"use client"

import React, { useEffect, useRef, useState } from "react";
import { Room, connect, LocalAudioTrack, createLocalAudioTrack } from "livekit-client";

/**
 * Day 5 Next.js Frontend (single-file)
 * Place this file at: `app/page.tsx` (Next.js 13+ app router) or `pages/index.tsx` for pages router
 * TailwindCSS recommended for styling. This file is a single-file demo — break into components in production.
 *
 * FEATURES
 * - Request LiveKit token from backend (/api/livekit/token)
 * - Connect to LiveKit room and publish local audio
 * - Show simple transcript area (assumes backend ASR or LiveKit voice events feed transcripts)
 * - Send user text to backend agent endpoint (/api/agent/message) and display text replies
 * - Simple lead form UI bound to the conversation
 * - End-call summary and download lead.json
 *
 * Required backend endpoints (implement in your Python/Node backend):
 * 1) GET /api/livekit/token?room=<room>&identity=<identity>
 *    - returns { token: "<access_token>", url: "wss://..." }
 * 2) POST /api/agent/message  (optional — you can also rely on LiveKit agents SDK running server-side)
 *    - body: { text: string }
 *    - response: { reply: string }
 * 3) GET /api/faq  -> returns company FAQ JSON
 * 4) POST /api/save-lead -> accepts lead JSON and persists
 *
 * ENV
 * - NEXT_PUBLIC_LIVEKIT_URL (optional if your token includes it)
 *
 */

export default function Page() {
  const [room, setRoom] = useState<Room | null>(null);
  const [connected, setConnected] = useState(false);
  const [identity, setIdentity] = useState("");
  const [roomName, setRoomName] = useState("ola-sdr-room");
  const [transcript, setTranscript] = useState<string[]>([]);
  const [messages, setMessages] = useState<{ from: string; text: string }[]>([]);
  const [faq, setFaq] = useState<any>(null);
  const audioTrackRef = useRef<LocalAudioTrack | null>(null);
  const [lead, setLead] = useState({
    name: "",
    company: "",
    email: "",
    role: "",
    use_case: "",
    team_size: "",
    timeline: "",
  });
  const [isConnecting, setIsConnecting] = useState(false);

  useEffect(() => {
    // load FAQ on mount
    (async () => {
      try {
        const r = await fetch("/api/faq");
        if (r.ok) setFaq(await r.json());
      } catch (e) {
        console.warn("Could not load FAQ", e);
      }
    })();

    return () => {
      disconnectRoom();
    };
  }, []);

  async function getLivekitToken(room: string, identity: string) {
    const res = await fetch(`/api/livekit/token?room=${encodeURIComponent(room)}&identity=${encodeURIComponent(identity)}`);
    if (!res.ok) throw new Error("Failed to get token");
    return res.json(); // { token, url }
  }

  async function connectToRoom() {
    if (!identity) return alert("Please enter your name/identity first");
    setIsConnecting(true);
    try {
      const { token, url } = await getLivekitToken(roomName, identity);
      const lkRoom = await connect(url || process.env.NEXT_PUBLIC_LIVEKIT_URL || "", token, {
        // optional options
        publishDefaults: { simulcast: false },
      });

      // create and publish local mic track
      const track = await createLocalAudioTrack();
      audioTrackRef.current = track;
      await lkRoom.localParticipant.publishTrack(track);

      lkRoom.on("participantConnected", (p) => {
        console.log("participantConnected", p.identity);
      });

      // subscribe to events: if your server publishes transcript messages into data channel
      lkRoom.on("dataReceived", (payload, participant) => {
        // payload is Uint8Array, make string
        try {
          const text = new TextDecoder().decode(payload);
          // if your server uses JSON wrapper, parse it
          try {
            const json = JSON.parse(text);
            if (json.type === "agent_reply") {
              appendMessage("Agent", json.text);
            } else if (json.type === "transcript") {
              appendTranscript(json.text);
            }
          } catch (e) {
            // plain text fallback
            appendTranscript(text);
          }
        } catch (err) {
          console.warn("failed decode data", err);
        }
      });

      setRoom(lkRoom);
      setConnected(true);
    } catch (err) {
      console.error(err);
      alert("Connection failed: " + err.message);
    } finally {
      setIsConnecting(false);
    }
  }

  function disconnectRoom() {
    if (room) {
      try {
        room.disconnect();
      } catch (e) {}
      setRoom(null);
    }
    setConnected(false);
    audioTrackRef.current = null;
  }

  function appendTranscript(t: string) {
    setTranscript((s) => [...s, t]);
  }

  function appendMessage(from: string, text: string) {
    setMessages((m) => [...m, { from, text }]);
  }

  async function sendTextToAgent(text: string) {
    appendMessage("You", text);
    try {
      const r = await fetch("/api/agent/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const j = await r.json();
      appendMessage("Agent", j.reply || "(no reply)");
      // Optionally play agent audio by requesting backend to synthesize via Murf
      if (j.play_audio_url) {
        playAudioFromUrl(j.play_audio_url);
      }
    } catch (e) {
      console.warn("agent send failed", e);
    }
  }

  function playAudioFromUrl(url: string) {
    const a = new Audio(url);
    a.play().catch((e) => console.warn(e));
  }

  async function saveLead() {
    try {
      const r = await fetch("/api/save-lead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lead),
      });
      if (!r.ok) throw new Error("save failed");
      alert("Lead saved");
    } catch (e) {
      alert("Failed to save lead: " + e.message);
    }
  }

  function downloadLead() {
    const blob = new Blob([JSON.stringify(lead, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "lead.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-5xl mx-auto">
        <header className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Day 5 — Ola SDR Frontend (Next.js)</h1>
          <div className="flex gap-2 items-center">
            <input
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              placeholder="Your name or identity"
              className="px-3 py-2 border rounded"
            />
            <input
              value={roomName}
              onChange={(e) => setRoomName(e.target.value)}
              placeholder="room name"
              className="px-3 py-2 border rounded"
            />
            {!connected ? (
              <button
                className="px-4 py-2 bg-blue-600 text-white rounded"
                onClick={connectToRoom}
                disabled={isConnecting}
              >
                {isConnecting ? "Connecting..." : "Connect"}
              </button>
            ) : (
              <button className="px-4 py-2 bg-red-500 text-white rounded" onClick={disconnectRoom}>
                Disconnect
              </button>
            )}
          </div>
        </header>

        <main className="grid grid-cols-3 gap-6">
          <section className="col-span-2 bg-white p-4 rounded shadow">
            <h2 className="font-semibold mb-2">Live Transcript</h2>
            <div className="space-y-2 max-h-72 overflow-auto p-2 border rounded">
              {transcript.length === 0 && <div className="text-sm text-gray-500">No transcript yet.</div>}
              {transcript.map((t, i) => (
                <div key={i} className="text-sm">
                  {t}
                </div>
              ))}
            </div>

            <h2 className="font-semibold mt-4 mb-2">Messages</h2>
            <div className="space-y-2 max-h-60 overflow-auto p-2 border rounded">
              {messages.map((m, i) => (
                <div key={i} className={`p-2 rounded ${m.from === "You" ? "bg-blue-50" : "bg-gray-100"}`}>
                  <strong className="text-xs text-gray-600">{m.from}</strong>
                  <div className="text-sm">{m.text}</div>
                </div>
              ))}
            </div>

            <SendBox onSend={sendTextToAgent} />
          </section>

          <aside className="bg-white p-4 rounded shadow">
            <h3 className="font-semibold mb-2">Lead Capture</h3>
            <div className="space-y-2">
              {Object.keys(lead).map((k) => (
                <div key={k}>
                  <label className="block text-xs text-gray-600">{k.replace(/_/g, " ")}</label>
                  <input
                    className="w-full px-2 py-1 border rounded"
                    value={(lead as any)[k]}
                    onChange={(e) => setLead((s) => ({ ...s, [k]: e.target.value }))}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-3">
              <button className="px-3 py-1 bg-green-600 text-white rounded" onClick={saveLead}>
                Save Lead
              </button>
              <button className="px-3 py-1 bg-indigo-600 text-white rounded" onClick={downloadLead}>
                Download lead.json
              </button>
            </div>

            <h3 className="font-semibold mt-6 mb-2">FAQ (loaded from backend)</h3>
            <div className="max-h-48 overflow-auto text-sm text-gray-700">
              {faq?.faq?.length ? (
                faq.faq.map((f: any, i: number) => (
                  <div key={i} className="mb-2">
                    <strong className="text-xs">Q: {f.q}</strong>
                    <div className="text-xs text-gray-600">A: {f.a}</div>
                  </div>
                ))
              ) : (
                <div className="text-xs text-gray-500">FAQ not loaded.</div>
              )}
            </div>

            <div className="mt-6 text-xs text-gray-500">Tip: use the Send box to ask questions and the backend agent will reply (text/audio).</div>
          </aside>
        </main>
      </div>
    </div>
  );
}

function SendBox({ onSend }: { onSend: (t: string) => void }) {
  const [text, setText] = useState("");
  return (
    <div className="mt-3">
      <textarea
        className="w-full p-2 border rounded"
        value={text}
        rows={3}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type a message to the agent (eg: What types of rides do you have?)"
      />
      <div className="flex gap-2 mt-2">
        <button
          className="px-3 py-1 bg-blue-600 text-white rounded"
          onClick={() => {
            if (!text.trim()) return;
            onSend(text.trim());
            setText("");
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
