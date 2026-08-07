import { useState } from "react";
import api from "../api/client";
import DashboardLayout from "../layouts/DashboardLayout";

export default function UploadContent() {
  const [tab, setTab] = useState("pdf");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [file, setFile] = useState(null);
  const [videoFile, setVideoFile] = useState(null);
  const [status, setStatus] = useState("");

  /**
   * All six uploads follow the same shape, so they share one helper rather
   * than repeating the token/URL/error handling six times.
   * `config` allows per-call overrides — video transcription disables the
   * client timeout because it legitimately runs for minutes.
   */
  const submitUpload = async (endpoint, fields, messages, config = {}) => {
    setStatus(messages.pending);
    try {
      const formData = new FormData();
      for (const [key, value] of Object.entries(fields)) {
        formData.append(key, value);
      }
      const res = await api.post(endpoint, formData, config);
      setStatus(messages.success(res.data));
    } catch (err) {
      setStatus(err.response?.data?.detail || messages.failure);
    }
  };

  const chunkMessage = (data) => `Success — ${data.chunk_count} chunks created.`;

  const handlePdfUpload = (e) => {
    e.preventDefault();
    return submitUpload("/content/upload-pdf", { file }, {
      pending: "Uploading...", success: chunkMessage, failure: "Upload failed",
    });
  };

  const handleTextUpload = (e) => {
    e.preventDefault();
    return submitUpload("/content/paste-text", { title, text }, {
      pending: "Processing...", success: chunkMessage, failure: "Processing failed",
    });
  };

  const handleUrlUpload = (e) => {
    e.preventDefault();
    return submitUpload("/content/from-url", { url }, {
      pending: "Fetching URL...", success: chunkMessage, failure: "Fetch failed",
    });
  };

  const handleYoutubeUpload = (e) => {
    e.preventDefault();
    return submitUpload("/content/from-youtube", { url: youtubeUrl }, {
      pending: "Fetching transcript...", success: chunkMessage, failure: "Transcript fetch failed",
    });
  };

  const handleVideoUpload = (e) => {
    e.preventDefault();
    return submitUpload("/content/upload-video", { file: videoFile }, {
      pending: "Uploading and transcribing... this may take a while.",
      success: chunkMessage,
      failure: "Video transcription failed",
    }, { timeout: 0 }); // transcription can far exceed the default timeout
  };

  const handlePaperUpload = (e) => {
    e.preventDefault();
    return submitUpload("/content/upload-research-paper", { file }, {
      pending: "Processing...",
      success: (data) =>
        `Success — ${data.chunk_count} chunks. Abstract detected: ${data.abstract_detected}`,
      failure: "Upload failed",
    });
  };

  const tabButtonStyle = (name) => ({
    marginRight: "0.5rem",
    fontWeight: tab === name ? "bold" : "normal",
    textDecoration: tab === name ? "underline" : "none",
  });

  return (
    <DashboardLayout title="Upload Content">
      <div style={{ marginBottom: "1rem" }}>
        <button style={tabButtonStyle("pdf")} onClick={() => setTab("pdf")}>PDF</button>
        <button style={tabButtonStyle("text")} onClick={() => setTab("text")}>Paste Text</button>
        <button style={tabButtonStyle("url")} onClick={() => setTab("url")}>Website URL</button>
        <button style={tabButtonStyle("youtube")} onClick={() => setTab("youtube")}>YouTube</button>
        <button style={tabButtonStyle("video")} onClick={() => setTab("video")}>Upload Video</button>
        <button style={tabButtonStyle("paper")} onClick={() => setTab("paper")}>Research Paper</button>
      </div>

      {tab === "pdf" && (
        <form onSubmit={handlePdfUpload}>
          <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files[0])} required />
          <button type="submit" style={{ marginLeft: "0.5rem" }}>Upload PDF</button>
        </form>
      )}

      {tab === "text" && (
        <form onSubmit={handleTextUpload}>
          <input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} required
            style={{ display: "block", marginBottom: "0.5rem", padding: "0.5rem", width: "100%" }} />
          <textarea placeholder="Paste text here" value={text} onChange={(e) => setText(e.target.value)} required rows={6}
            style={{ display: "block", marginBottom: "0.5rem", padding: "0.5rem", width: "100%" }} />
          <button type="submit">Process Text</button>
        </form>
      )}

      {tab === "url" && (
        <form onSubmit={handleUrlUpload}>
          <input placeholder="https://example.com/article" value={url} onChange={(e) => setUrl(e.target.value)} required
            style={{ display: "block", marginBottom: "0.5rem", padding: "0.5rem", width: "100%" }} />
          <button type="submit">Fetch & Process</button>
        </form>
      )}

      {tab === "youtube" && (
        <form onSubmit={handleYoutubeUpload}>
          <input placeholder="https://www.youtube.com/watch?v=..." value={youtubeUrl} onChange={(e) => setYoutubeUrl(e.target.value)} required
            style={{ display: "block", marginBottom: "0.5rem", padding: "0.5rem", width: "100%" }} />
          <button type="submit">Fetch Transcript</button>
        </form>
      )}

      {tab === "video" && (
        <form onSubmit={handleVideoUpload}>
          <input type="file" accept="video/mp4,video/quicktime,video/x-msvideo,video/webm" onChange={(e) => setVideoFile(e.target.files[0])} required />
          <button type="submit" style={{ marginLeft: "0.5rem" }}>Upload & Transcribe</button>
          <p style={{ fontSize: "0.85rem", color: "#666", marginTop: "0.5rem" }}>
            Note: video transcription requires backend configuration and may not be active yet.
          </p>
        </form>
      )}

      {tab === "paper" && (
        <form onSubmit={handlePaperUpload}>
          <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files[0])} required />
          <button type="submit" style={{ marginLeft: "0.5rem" }}>Upload Research Paper</button>
         </form>
      )}

      {status && <p style={{ marginTop: "1rem" }}>{status}</p>}
    </DashboardLayout>
  );
}