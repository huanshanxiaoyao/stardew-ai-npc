using HarmonyLib;
using StardewAiMod.Patches;
using StardewModdingAPI;

namespace StardewAiMod
{
    public class ModEntry : Mod
    {
        public override void Entry(IModHelper helper)
        {
            NpcCheckActionPatch.Initialize(this.Monitor);

            var harmony = new Harmony(this.ModManifest.UniqueID);
            harmony.PatchAll();

            this.Monitor.Log("StardewAiMod loaded; Harmony patches applied.", LogLevel.Info);
        }
    }
}
