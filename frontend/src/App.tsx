import { useState } from 'react'
import { generateSpeech } from './lib/api'
import { useAppStore } from './store'

export default function App() {
  const { text, setText, audioUrl, setAudioUrl, isGenerating, setGenerating, error, setError } =
    useAppStore()
  const [language, setLanguage] = useState('English')

  async function handleGenerate() {
    if (!text.trim() || isGenerating) return
    setGenerating(true)
    setError(null)
    try {
      const blob = await generateSpeech({ text, language, responseFormat: 'mp3' })
      if (audioUrl) URL.revokeObjectURL(audioUrl)
      setAudioUrl(URL.createObjectURL(blob))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-10">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Qwen3-TTS</h1>
        <p className="text-sm text-neutral-400">Type text, hear it spoken by the cloned base voice.</p>
      </header>

      <textarea
        className="min-h-40 resize-y rounded-lg border border-neutral-800 bg-neutral-900 p-4 text-base outline-none focus:border-neutral-600"
        placeholder="Say something..."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <div className="flex items-center gap-3">
        <select
          className="rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
        >
          <option>English</option>
          <option>Chinese</option>
        </select>

        <button
          className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 disabled:opacity-40"
          onClick={handleGenerate}
          disabled={!text.trim() || isGenerating}
        >
          {isGenerating ? 'Generating…' : 'Generate'}
        </button>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {audioUrl && <audio className="w-full" controls autoPlay src={audioUrl} />}
    </div>
  )
}
