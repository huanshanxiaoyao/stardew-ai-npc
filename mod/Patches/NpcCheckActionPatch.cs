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

        public static void Initialize(IMonitor monitor)
        {
            Monitor = monitor;
        }

        public static bool Prefix(NPC __instance, Farmer who, GameLocation l, ref bool __result)
        {
            if (!Context.IsWorldReady)
                return true;

            Monitor?.Log($"Intercepted checkAction on NPC '{__instance.Name}'.", LogLevel.Debug);

            Game1.activeClickableMenu = new DialogueBox("Hello from AI Mod!");
            __result = true;
            return false;
        }
    }
}
