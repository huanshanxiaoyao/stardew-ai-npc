using System;
using System.Collections.Generic;
using HarmonyLib;
using StardewAiMod.Net;
using StardewAiMod.Patches;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;
using StardewValley.Menus;

namespace StardewAiMod
{
    public class ModEntry : Mod
    {
        private const string BridgeUrl = "ws://127.0.0.1:8765";
        private const double ReplyTimeoutSeconds = 12.0;

        private BridgeClient? _bridge;

        // id → (npc, deadlineUtc, placeholderMenu); accessed only on main thread.
        private readonly Dictionary<string, InflightRequest> _inflight = new();
        private readonly HashSet<string> _cancelledIds = new();

        public BridgeClient Bridge => _bridge!;
        public IReadOnlyDictionary<string, InflightRequest> Inflight => _inflight;

        public override void Entry(IModHelper helper)
        {
            _bridge = new BridgeClient(BridgeUrl, this.Monitor);
            _bridge.Start();

            // NOTE: Initialize signature is updated in Task 13 to also pass `this`.
            // Until then the patch keeps using its hardcoded "Hello from AI Mod!" reply,
            // which is fine — this task only adds the bridge plumbing on the ModEntry side.
            NpcCheckActionPatch.Initialize(this.Monitor);

            var harmony = new Harmony(this.ModManifest.UniqueID);
            harmony.PatchAll();

            helper.Events.GameLoop.UpdateTicked += this.OnUpdateTicked;
            helper.Events.GameLoop.ReturnedToTitle += this.OnReturnedToTitle;

            this.Monitor.Log("StardewAiMod loaded; Harmony + bridge active.", LogLevel.Info);
        }

        public void RegisterInflight(string id, string npc, IClickableMenu placeholder)
        {
            _inflight[id] = new InflightRequest(npc, DateTime.UtcNow.AddSeconds(ReplyTimeoutSeconds), placeholder);
        }

        public bool HasInflightForNpc(string npc)
        {
            foreach (var kv in _inflight)
                if (kv.Value.Npc == npc) return true;
            return false;
        }

        private void OnUpdateTicked(object? sender, UpdateTickedEventArgs e)
        {
            // Drain replies.
            while (_bridge!.ReplyQueue.TryDequeue(out var reply))
            {
                if (_cancelledIds.Remove(reply.Id))
                {
                    this.Monitor.Log($"Discarding reply for cancelled id={reply.Id}.", LogLevel.Trace);
                    continue;
                }
                if (!_inflight.TryGetValue(reply.Id, out var info))
                {
                    this.Monitor.Log($"Reply for unknown id={reply.Id}; dropping.", LogLevel.Trace);
                    continue;
                }
                _inflight.Remove(reply.Id);

                // Replace placeholder iff it is still our menu.
                if (Game1.activeClickableMenu == info.Placeholder)
                    Game1.activeClickableMenu = new DialogueBox(reply.Text);
                // else: player dismissed it; do nothing.
            }

            // Watch for player-dismissed placeholders → mark cancelled.
            if (_inflight.Count > 0)
            {
                List<string>? toCancel = null;
                var now = DateTime.UtcNow;
                foreach (var kv in _inflight)
                {
                    if (Game1.activeClickableMenu != kv.Value.Placeholder)
                    {
                        (toCancel ??= new()).Add(kv.Key);
                    }
                    else if (now > kv.Value.DeadlineUtc)
                    {
                        (toCancel ??= new()).Add(kv.Key);
                        Game1.activeClickableMenu = new DialogueBox("…(NPC didn't speak)");
                    }
                }
                if (toCancel != null)
                {
                    foreach (var id in toCancel)
                    {
                        _inflight.Remove(id);
                        _cancelledIds.Add(id);
                    }
                }
            }
        }

        private void OnReturnedToTitle(object? sender, ReturnedToTitleEventArgs e)
        {
            _inflight.Clear();
            _cancelledIds.Clear();
            _bridge?.SendSessionReset("returned_to_title");
        }
    }

    public record InflightRequest(string Npc, DateTime DeadlineUtc, IClickableMenu Placeholder);
}
