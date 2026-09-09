// UI captions only. The actual function identifiers must stay stable for tool calls.
export function getToolDisplayName(
	name: string | undefined,
	translate: (key: string) => string
): string {
	if (name === 'research_uzbek_law') return 'LexUz';
	if (name === 'create_document') return translate('Document creation');
	if (name === 'create_spreadsheet') return translate('Spreadsheet creation');
	if (name === 'research_prosecutor_orders') return translate('Prosecutor General’s orders');
	if (name === 'search_encyclopedia') return translate('Encyclopedia search');
	return name ?? '';
}

// Workspace model/tool captions live in the database (name, meta.description) and are
// authored in English. Known ones are shown through i18n; anything else stays verbatim.
const WORKSPACE_CAPTIONS = new Set([
	'Unified assistant with documents, LexUz and Bosh prokuror buyruqlari.',
	'LexUz / Bosh prokuror buyruqlari',
	'Signed, permission-aware legal research for ProkuraturaAI.',
	'Word / PDF / Excel',
	'Private document generation; downloads expire after 30 days.',
	'Encyclopedia (offline Wikipedia)',
	'Offline Uzbek and Russian Wikipedia search; no internet access.'
]);

export function getWorkspaceCaption(
	text: string | undefined | null,
	translate: (key: string) => string
): string {
	const value = (text ?? '').trim();
	return WORKSPACE_CAPTIONS.has(value) ? translate(value) : (text ?? '');
}
