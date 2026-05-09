using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using StardewModdingAPI;

namespace StardewAiMod.Net
{
    /// <summary>
    /// Long-lived WebSocket client to the Python bridge.
    /// Reconnects with exponential backoff. All public callers are on the game's main thread;
    /// internal work runs on background tasks. Replies arrive on the ReplyQueue; ModEntry drains it
    /// during UpdateTicked so all UI calls happen on the main thread.
    /// </summary>
    public sealed class BridgeClient
    {
        private readonly Uri _uri;
        private readonly IMonitor _monitor;
        private readonly CancellationTokenSource _cts = new();
        private readonly SemaphoreSlim _sendLock = new(1, 1);
        private ClientWebSocket? _ws;
        private volatile bool _isConnected;

        public ConcurrentQueue<NpcReply> ReplyQueue { get; } = new();
        public bool IsConnected => _isConnected;

        public BridgeClient(string url, IMonitor monitor)
        {
            _uri = new Uri(url);
            _monitor = monitor;
        }

        public void Start()
        {
            _ = Task.Run(() => ConnectLoopAsync(_cts.Token));
        }

        public void Stop()
        {
            _cts.Cancel();
            try { _ws?.Abort(); } catch { /* best effort */ }
        }

        public string? SendNpcInteract(string npcName, string playerName, string location)
        {
            if (!_isConnected || _ws is null || _ws.State != WebSocketState.Open) return null;
            var id = Guid.NewGuid().ToString("N");
            var msg = new NpcInteract(id, npcName, playerName, location, DateTimeOffset.UtcNow.ToUnixTimeSeconds());
            _ = SendJsonAsync(JsonSerializer.Serialize(msg));
            return id;
        }

        public void SendSessionReset(string reason)
        {
            if (!_isConnected || _ws is null || _ws.State != WebSocketState.Open) return;
            var msg = new SessionReset(reason);
            _ = SendJsonAsync(JsonSerializer.Serialize(msg));
        }

        private async Task SendJsonAsync(string json)
        {
            // ClientWebSocket.SendAsync only supports one outstanding send at a time.
            await _sendLock.WaitAsync(_cts.Token);
            try
            {
                var ws = _ws;
                if (ws is null || ws.State != WebSocketState.Open) return;
                var bytes = Encoding.UTF8.GetBytes(json);
                await ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
            }
            catch (Exception ex)
            {
                _monitor.Log($"Bridge: send failed: {ex.Message}", LogLevel.Warn);
            }
            finally
            {
                try { _sendLock.Release(); } catch (ObjectDisposedException) { }
            }
        }

        private async Task ConnectLoopAsync(CancellationToken ct)
        {
            int delayMs = 1000;
            while (!ct.IsCancellationRequested)
            {
                _ws = new ClientWebSocket();
                try
                {
                    _monitor.Log($"Bridge: connecting to {_uri}", LogLevel.Trace);
                    await _ws.ConnectAsync(_uri, ct);
                    _isConnected = true;
                    delayMs = 1000;
                    _monitor.Log("Bridge: connected.", LogLevel.Info);
                    await ReceiveLoopAsync(_ws, ct);
                }
                catch (OperationCanceledException) { break; }
                catch (Exception ex)
                {
                    _monitor.Log($"Bridge: connect/receive error: {ex.Message}", LogLevel.Trace);
                }
                finally
                {
                    _isConnected = false;
                    try { _ws?.Dispose(); } catch { }
                }

                if (ct.IsCancellationRequested) break;
                try { await Task.Delay(delayMs, ct); } catch { break; }
                delayMs = Math.Min(delayMs * 2, 10000);
            }
        }

        private async Task ReceiveLoopAsync(ClientWebSocket ws, CancellationToken ct)
        {
            var buffer = new byte[8192];
            var sb = new StringBuilder();
            while (!ct.IsCancellationRequested && ws.State == WebSocketState.Open)
            {
                sb.Clear();
                WebSocketReceiveResult result;
                do
                {
                    result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", ct);
                        return;
                    }
                    sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                } while (!result.EndOfMessage);

                var raw = sb.ToString();
                NpcReply? reply = null;
                try
                {
                    using var doc = JsonDocument.Parse(raw);
                    var type = doc.RootElement.GetProperty("type").GetString();
                    if (type == "npc_reply")
                        reply = JsonSerializer.Deserialize<NpcReply>(raw);
                    else
                        _monitor.Log($"Bridge: ignoring message of type '{type}'.", LogLevel.Trace);
                }
                catch (Exception ex)
                {
                    _monitor.Log($"Bridge: parse error: {ex.Message}; raw={raw}", LogLevel.Warn);
                    continue;
                }

                if (reply != null) ReplyQueue.Enqueue(reply);
            }
        }
    }
}
