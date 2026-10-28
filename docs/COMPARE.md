# Compare engines (blind A/B)

**Voice Library → Compare** renders the same text on two to four engine/voice slots, lets you rate the clips
without knowing which engine made which, and keeps your ratings. It exists because no engine has been ranked
best: the plan only records measurements and a few listening sessions ([plan §5.5, §5.10](archive/multi-engine-speech/20261023-kokoro_phonon_kittentts2.md)).
Install engines first: [Speech engines](SPEECH_ENGINES.md). Saved voices and Prepare: [Voices](VOICES.md).

## Run a comparison

1. Type the **Text**, or use one of the three sample sentences. One is structured text (an invoice number, money
   and a time), the kind of text that exposed a real misreading in the bake-off.
2. Fill the **slots** (2 to 4; **Add slot** and the remove button adjust them). Each slot is an engine and a voice:
   a built-in voice of that engine, or a saved voice on an engine that clones. Engines that are not installed read
   "(install to compare)"; one that is still loading reads "(loading)" or "(warming up)".
3. **Same voice on every cloning engine** fills up to four slots with one saved voice on every installed engine
   that can clone it. It needs a saved voice and at least two such engines. You can also start from a saved voice's
   **Compare engines** action.
4. Leave **Blind mode** on to hide engine names (it is on by default), then **Generate**. Slots are generated one
   after another through `/v1/audio/speech`, each showing how long it took and how much audio it made. A slot that
   fails shows its error and does not block the others. Time spent waiting for an engine that was still loading is
   subtracted from the generation time.
5. With a saved voice in a slot, the **reference clip** plays first with its transcript ("No transcript saved for
   this voice." if it has none), so "sounds like the reference" is judged against something you just heard.
6. Play each clip (A, B, C, D in shuffled order). Rate **Natural**, **Clean (no artifacts)** and, for cloned voices
   only, **Sounds like the reference**, each 1-5, and pick one **Favourite**. A rating you do not touch is saved as 3
   and counts in the averages.
7. **Reveal engines and save ratings** shows which engine was which and saves the session. With blind mode off the
   button is **Save ratings**.

Playback is **level-matched** to about −23 dB RMS in the browser, and the clips come through the server's loudness
normalisation as well (on by default; see [Speech engines](SPEECH_ENGINES.md#serving-an-engine-from-the-api)), so
loudness should not decide the result.

## Your ratings

- Saved sessions live on the server (`compare_results.json` beside the UI preferences), so every browser sees the
  same ratings. The table under the results shows, per engine, the clip count, average Natural, Clean and Similar,
  favourites, and generation speed as median / worst seconds of compute per second of audio.
- Each engine card in **Runtime → Speech engines** shows "Your ratings: N natural, N clean (clips)" once you have
  some.
- **Clear saved ratings** deletes them all. At most 500 sessions are kept (the newest).
- The ratings are subjective and depend on the text and voice you tried. They are not a ranking.

## Auto-check hints (optional)

Under each clip, **Auto-check (hint)** can show two numbers computed on your computer:

- **Word error:** what a small speech recognizer (faster-whisper `tiny.en`) heard compared with your text, as a
  percentage, with the words it heard. Numbers, money, times and codes are spelled out on both sides, and case,
  punctuation and hyphens are ignored, so "10 minutes" against "ten minutes" is not an error.
- **Speaker similarity** (cloned voices only): how close the clip is to the saved voice's reference clip, from a
  speaker-verification model (WavLM-SV); 1 is identical.

How it behaves:

- **Off until you ask.** A box offers "Enable auto-check: download models (N MB)": 78 MB for the recognizer and 405 MB
  for the similarity model (483 MB together). Nothing is downloaded before you click, and checks run offline from
  those local copies. Models that are already in your Hugging Face cache are reused.
- **Hidden until you reveal.** In blind mode the hints (and the download box) appear only after the reveal, so
  they cannot hint at the engine or sway the ratings. A note says so.
- **One check at a time**, on a clip you click **Check** for. The models are released after 120 s idle
  (`AUTOCHECK_IDLE_UNLOAD_SECONDS`). Auto-check does not use the speech queue, but it does share the CPU: in the
  plan's worst-case loop, back-to-back checks slowed concurrent Pocket requests by about 16%.
- Clips over 120 s or 25 MB, and text over 5000 characters, are refused.

What the hints are **not**:

- **Not a quality score.** The similarity metric is not calibrated for synthetic voices: in the bake-off even
  different speakers scored about 0.85. The page says "never replaces the rating", and it does not.
- **English only**: the recognizer is `tiny.en`. Non-English text was not checked.
- **A hint, not a verdict, for word error.** The tiny recognizer mishears real words ("invoice" as "in voice"), and
  a bare "AB 104" is read as a number while "AB-104" is read digit by digit, so one word can count wrongly. On the plan's structured sentence,
  Pocket and Kitten 2 scored 29% and 36% before time and acronym handling was added and 3.8% and 15% after; each
  run is a fresh synthesis, so the numbers move.
- **Not stored.** Scores are not saved with your ratings and do not feed the engine summary.
- **Not validated against human listeners.** The plan records no comparison.

## Known limitations

- **Verified on one Apple-silicon Mac with real packs.** Windows and Linux were not exercised through the Compare
  tab; Linux CUDA is untested ([Speech engines](SPEECH_ENGINES.md#known-limitations)).
- **Generation is serial and uses the same engines as the API**, so a cold engine adds its load time before the
  first clip. A slow first slot is not a slow engine; the speed column uses the time minus any warm-up wait.
- **Speed numbers are per machine and per load.** A few runs on a busy computer will read slower.
- **No saved audio.** Clips live in the browser until you leave the page; only the ratings are stored.
- **Small samples.** The plan's listening notes come from one listener, eight clips per engine per round, on a few
  references; the owner's own recordings and male voices were untested.
- **Auto-check limits** are listed above: unvalidated, English only, not stored, off until you download the models.
