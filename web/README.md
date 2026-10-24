# FinLint web

The product interface: Next.js 14, React 18, TypeScript in strict mode,
Tailwind, Radix primitives, framer-motion and Recharts.

## Run it

```bash
npm install
npm run dev
```

Then open http://localhost:3000.

## Two modes, and it tells you which

On start the app asks `GET /api/health` on port 8000.

- **Live.** The API answered, so every call goes to it. Uploading, citations
  and decisions all hit the real engine and the run history in PostgreSQL.
- **Saved sample.** The API did not answer, so the app reads `public/fixtures/`
  and shows a blue banner saying so. Those files are a real run of the real
  engine on `Financial_Models.xlsx`, exported by
  `scripts/export_ui_fixture.py`. Nothing in them is invented.

In a saved sample, checking a new workbook is refused with a reason, because
it needs the engine. A decision you record is kept in this browser only, and
the dialog says so.

To refresh the sample from the current backend, with PostgreSQL running:

```bash
python scripts/export_ui_fixture.py --explain 4
```

`--explain 4` asks the Standards agent about one finding per rule, which costs
real Groq calls. Leave it off and the saved explanations are kept.

## The contract

`docs/api_contract.md` is the agreement between this frontend and
`src/finlint/api/main.py`. `lib/types.ts` mirrors it exactly. If they ever
disagree, the contract wins.

## Ship it

```bash
npm run build
```

This writes plain static files to `out/`. The FastAPI app can serve that folder
itself, so the whole product is one container and one URL, with the frontend
calling `/api` on the same origin.

## Deliberate choices worth knowing

- **No "fix" button.** FinLint never changes a workbook. The only action on a
  finding records a person's decision and their reason. See CLAUDE.md Section
  10.
- **Citations are labelled context, not proof.** A verified passage supports a
  review; it does not prove a cell is wrong.
- **No ligatures in monospace.** JetBrains Mono would otherwise draw `<=` as one
  glyph, showing a character that is not in the formula.
- **The rule id is a caption, not a column.** It says the same thing as the
  rule's name, so a separate column only cost width.
