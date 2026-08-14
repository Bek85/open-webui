#!/usr/bin/env node
/**
 * Build gate: catch identifiers that are USED but never IMPORTED in .svelte files.
 *
 * Why this exists: `vite build` compiles Svelte templates without resolving
 * identifier scope, so a used-but-unimported variable builds cleanly and only
 * throws `ReferenceError` in the browser. That is exactly how the v0.11.0
 * upstream merge shipped a broken UI to prod on 2026-08-14 — the merge kept the
 * fork's timestamp-tooltip template in ResponseMessage.svelte but resolved the
 * import block to the other side, dropping `dayjs` and `formatDate`. The backend
 * streamed fine; no assistant output ever painted. Fixed in 1d091a0d0.
 *
 * Why not the standard tools:
 *   - `npm run check` (svelte-check) reports ~8274 pre-existing errors upstream,
 *     so it cannot be a blocking gate without a massive cleanup.
 *   - `eslint` (8.57.1) crashes outright on this tree post-v0.11.0.
 * So this stays deliberately narrow: one bug class, zero tolerance, no config.
 *
 * Scope: names exported from $lib/utils plus a few common default imports.
 * That covers the merge-artifact shape (template takes theirs, imports keep ours)
 * without trying to be a general linter.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const SRC = 'src';
const UTILS = 'src/lib/utils/index.ts';
// Default-imported modules whose absence produced runtime ReferenceErrors before.
const DEFAULT_IMPORTS = ['dayjs', 'marked', 'equal', 'hljs'];

/** Recursively collect every .svelte file under a directory. */
const walk = (dir, out = []) => {
	for (const entry of readdirSync(dir)) {
		const p = join(dir, entry);
		if (statSync(p).isDirectory()) walk(p, out);
		else if (p.endsWith('.svelte')) out.push(p);
	}
	return out;
};

const exported = [
	...readFileSync(UTILS, 'utf8').matchAll(/^export (?:const|function) (\w+)/gm)
].map((m) => m[1]);

const candidates = [...new Set([...exported, ...DEFAULT_IMPORTS])];

const findings = [];
for (const file of walk(SRC)) {
	const text = readFileSync(file, 'utf8');

	// The import surface: `import ...` lines plus the bare-identifier lines that
	// make up multi-line `import { a, b } from '...'` blocks.
	const importSurface = text
		.split('\n')
		.filter((l) => /^\s*import\b/.test(l) || /^\s+\w+,?\s*$/.test(l))
		.join('\n');

	for (const name of candidates) {
		// Used as a call, not as a property access (`.name(`) or `$name(`.
		const used = new RegExp(`(?<![\\w.$])${name}\\s*\\(`).test(text);
		if (!used) continue;

		// Imported directly, or aliased (`name as _name`).
		if (new RegExp(`(?<![\\w.$])${name}(?![\\w])`).test(importSurface)) continue;

		// Declared locally in this component — not an import at all.
		if (new RegExp(`(?:const|let|var|function|async function)\\s+${name}\\b`).test(text)) continue;

		findings.push({ file, name });
	}
}

if (findings.length) {
	console.error('\nMissing imports — these build fine but throw ReferenceError in the browser:\n');
	for (const { file, name } of findings) console.error(`  ${name.padEnd(24)} ${file}`);
	console.error(`\n${findings.length} missing import(s). Add them, or the UI breaks at runtime.\n`);
	process.exit(1);
}

console.log(`check-missing-imports: ok (${candidates.length} names checked)`);
