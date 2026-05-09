using System;
using System.Text.Json.Serialization;

namespace StardewAiMod.Net
{
    public record GameDate(
        [property: JsonPropertyName("year")] int Year,
        [property: JsonPropertyName("season")] string Season,
        [property: JsonPropertyName("day")] int Day,
        [property: JsonPropertyName("dayOfWeek")] string DayOfWeek);

    public record GameState(
        [property: JsonPropertyName("date")] GameDate Date,
        [property: JsonPropertyName("weather")] string Weather,
        [property: JsonPropertyName("spouse")] string? Spouse,
        [property: JsonPropertyName("activeQuests")] string[] ActiveQuests);

    public record NpcInteract(
        [property: JsonPropertyName("id")] string Id,
        [property: JsonPropertyName("npc")] string Npc,
        [property: JsonPropertyName("player")] string Player,
        [property: JsonPropertyName("location")] string Location,
        [property: JsonPropertyName("ts")] long Ts,
        [property: JsonPropertyName("state")] GameState? State
    )
    {
        [JsonPropertyName("type")]
        public string Type => "npc_interact";

        [JsonPropertyName("v")]
        public int V => 1;
    }

    public record NpcReply(
        [property: JsonPropertyName("id")] string Id,
        [property: JsonPropertyName("npc")] string Npc,
        [property: JsonPropertyName("text")] string Text,
        [property: JsonPropertyName("done")] bool Done
    )
    {
        [JsonPropertyName("type")]
        public string Type => "npc_reply";

        [JsonPropertyName("v")]
        public int V => 1;
    }

    public record SessionReset(
        [property: JsonPropertyName("reason")] string Reason
    )
    {
        [JsonPropertyName("type")]
        public string Type => "session_reset";

        [JsonPropertyName("v")]
        public int V => 1;
    }
}
