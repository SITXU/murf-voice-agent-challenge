// frontend/pages/day4.js
import { useState } from "react";

export default function Day4() {
  const [session, setSession] = useState(null);
  const [message, setMessage] = useState("");
  const [lastResponse, setLastResponse] = useState(null);
  const [answerText, setAnswerText] = useState("");
  const apiBase = "http://127.0.0.1:9004"; // backend

  function speak(text, voiceName) {
    if (!window.speechSynthesis) return;
    const utter = new SpeechSynthesisUtterance(text);
    // try match voice by name (best-effort). Browser voices vary.
    const voices = window.speechSynthesis.getVoices();
    const found = voices.find(v => (v.name || "").toLowerCase().includes((voiceName||"").toLowerCase()));
    if (found) utter.voice = found;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
  }

  async function startSession() {
    const res = await fetch(`${apiBase}/start_session`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ user_name: "Simran" }),
    });
    const j = await res.json();
    setSession(j.session_id);
    setMessage(j.greeting);
    speak(j.greeting, "Matthew");
  }

  async function setMode(mode) {
    if (!session) { alert("Start session first"); return; }
    const res = await fetch(`${apiBase}/set_mode`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ session_id: session, mode }),
    });
    const j = await res.json();
    setLastResponse(j);
    if (j.action_text) {
      setMessage(j.action_text);
      speak(j.action_text, j.voice);
    } else if (j.question) {
      setMessage(j.question);
      speak(j.question, j.voice);
    } else if (j.prompt) {
      setMessage(j.prompt);
      speak(j.prompt, j.voice);
    }
  }

  async function submitAnswer() {
    if (!session || !lastResponse) { alert("Start session and choose a concept first"); return; }
    const conceptId = lastResponse.concept.id;
    const res = await fetch(`${apiBase}/submit_answer`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ session_id: session, concept_id: conceptId, answer_text: answerText }),
    });
    const j = await res.json();
    setMessage(`Score: ${j.score.toFixed(2)} — ${j.feedback}`);
    speak(`Your score is ${Math.round(j.score*100)} percent. ${j.feedback}`, "Ken");
  }

  return (
    <div style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1>Day 4 — Teach-the-Tutor</h1>
      <button onClick={startSession}>Start Session</button>
      <div style={{ marginTop: 12 }}>
        <button onClick={() => setMode("learn")}>Learn</button>
        <button onClick={() => setMode("quiz")}>Quiz</button>
        <button onClick={() => setMode("teach_back")}>Teach Back</button>
      </div>

      <div style={{ marginTop: 16, padding: 12, border: "1px solid #ddd", maxWidth: 800 }}>
        <strong>Agent says:</strong>
        <p>{message}</p>

        <textarea
          rows={4}
          cols={80}
          placeholder="Type your answer / teach-back here..."
          value={answerText}
          onChange={(e) => setAnswerText(e.target.value)}
        />
        <div>
          <button onClick={submitAnswer}>Submit Answer</button>
        </div>
      </div>

      <div style={{ marginTop: 18, color: "#666" }}>
        <small>Note: you can replace the browser TTS with Murf or server-side TTS later.</small>
      </div>
    </div>
  );
}
