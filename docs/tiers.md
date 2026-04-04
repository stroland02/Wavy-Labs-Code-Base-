# Tiers & Pricing

Wavy Labs operates on a **freemium + subscription** model.
The core DAW is always free and open source. AI features are gated by tier.

## Plans

| Feature | Free | Pro | Studio |
|---------|------|-----|--------|
| **Price** | $0 | $9.99/mo | $24.99/mo |
| Full LMMS DAW | ✅ | ✅ | ✅ |
| AI Music Generation | 5/day | Unlimited | Unlimited |
| Stem Splitting | 2-stem | 6-stem | 6-stem |
| Vocal Generation | — | ✅ | ✅ |
| AI Mix & Master | — | ✅ | ✅ |
| Prompt Commands | — | — | ✅ |
| Code to Music | — | — | ✅ |
| Priority GPU processing | — | — | ✅ |

---

## Free Tier

- Full LMMS DAW with no limitations
- **5 AI generations per day** (resets at midnight local time)
- "Best of 3" counts as 3 generations
- 2-stem split (vocals + accompaniment)
- No credit card required

---

## Pro ($9.99/month)

Everything in Free, plus:

- **Unlimited AI music generation**
- **6-stem splitting** (vocals, drums, bass, guitar, piano, other)
- **Vocal Generation** (Bark, 10 voice presets)
- **AI Mix Assist** — automatic EQ/compression suggestions as automation
- **AI Mastering** — loudness normalization + limiting (–14 LUFS target)
- Reference track mode for mix matching

---

## Studio ($24.99/month)

Everything in Pro, plus:

- **Prompt Commands** — natural language DAW control (Ctrl+K)
- **Code to Music** — Monaco editor + Wavy DSL + data sonification
- Priority GPU slot on model inference queue
- Early access to new AI features

---

## License Validation

License keys are validated **locally** using HMAC-SHA256.
No internet connection is required for day-to-day use.

- Re-validation with the license server occurs every **7 days** when online.
- If re-validation cannot reach the server (offline), a **7-day grace period** applies.
- At the end of the grace period, the key reverts to Free tier until connectivity is restored.

License keys are stored securely using the OS credential store
(Windows Credential Manager / macOS Keychain / libsecret on Linux).

---

## Purchasing

Visit [wavylabs.io/pricing](https://wavylabs.io/pricing) to subscribe.
After purchase, enter your license key in **Settings → License → Activate**.
