using HarmonyLib;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Menus;

namespace StardewAiMod.Patches
{
    [HarmonyPatch(typeof(NPC), nameof(NPC.checkAction))]
    public static class NpcCheckActionPatch
    {
        private static IMonitor? Monitor;
        private static ModEntry? Mod;

        public static void Initialize(IMonitor monitor, ModEntry mod)
        {
            Monitor = monitor;
            Mod = mod;
        }

        public static bool Prefix(NPC __instance, Farmer who, GameLocation l, ref bool __result)
        {
            if (!Context.IsWorldReady || Mod is null) return true;

            var bridge = Mod.Bridge;
            if (!bridge.IsConnected)
            {
                Monitor?.Log($"Bridge not connected; falling back to native dialogue for {__instance.Name}.", LogLevel.Trace);
                return true;
            }

            if (Mod.HasInflightForNpc(__instance.Name))
            {
                Monitor?.Log($"Ignoring click on {__instance.Name}: request still in flight.", LogLevel.Trace);
                __result = true;
                return false;
            }

            var placeholder = new DialogueBox("…");
            Game1.activeClickableMenu = placeholder;

            var id = bridge.SendNpcInteract(__instance.Name, who.Name, l?.Name ?? "Unknown");
            if (id is null)
            {
                // Send failed (e.g. just disconnected). Drop the placeholder and let native run next click.
                Game1.activeClickableMenu = null;
                return true;
            }

            Mod.RegisterInflight(id, __instance.Name, placeholder);
            __result = true;
            return false;
        }
    }
}
