using System;
using System.Linq;
using StardewAiMod.Net;
using StardewModdingAPI;
using StardewValley;

namespace StardewAiMod.Game
{
    /// <summary>
    /// Reads SDV global state into a JSON-friendly snapshot.
    /// Best-effort: returns null if the world is not ready or any read throws,
    /// so a Stardew API hiccup never breaks NPC dialogue.
    /// </summary>
    public static class StateCollector
    {
        private static IMonitor? Monitor;
        private static readonly string[] DayNames = { "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun" };
        private const int MaxQuests = 5;

        public static void Initialize(IMonitor monitor)
        {
            Monitor = monitor;
        }

        public static GameState? Collect()
        {
            if (!Context.IsWorldReady) return null;

            try
            {
                var date = new GameDate(
                    Year: StardewValley.Game1.year,
                    Season: StardewValley.Game1.currentSeason ?? "spring",
                    Day: StardewValley.Game1.dayOfMonth,
                    DayOfWeek: DayNames[(StardewValley.Game1.dayOfMonth - 1) % 7]
                );

                var weather = ReadWeather();

                var spouse = StardewValley.Game1.player?.spouse;
                if (string.IsNullOrEmpty(spouse)) spouse = null;

                var quests = StardewValley.Game1.player?.questLog
                    ?.Take(MaxQuests)
                    .Select(q => q?.questTitle?.ToString() ?? "")
                    .Where(t => !string.IsNullOrEmpty(t))
                    .ToArray()
                    ?? Array.Empty<string>();

                return new GameState(date, weather, spouse, quests);
            }
            catch (Exception ex)
            {
                Monitor?.Log($"StateCollector failed: {ex.Message}", LogLevel.Trace);
                return null;
            }
        }

        private static string ReadWeather()
        {
            if (StardewValley.Game1.isLightning) return "stormy";
            if (StardewValley.Game1.isRaining) return "rainy";
            if (StardewValley.Game1.isSnowing) return "snowy";
            return "sunny";
        }
    }
}
