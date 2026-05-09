using StardewModdingAPI;

namespace StardewAiMod
{
    public class ModEntry : Mod
    {
        public override void Entry(IModHelper helper)
        {
            this.Monitor.Log("StardewAiMod loaded.", LogLevel.Info);
        }
    }
}
