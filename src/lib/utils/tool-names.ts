// UI captions only. The actual function identifiers must stay stable for tool calls.
export function getToolDisplayName(
	name: string | undefined,
	translate: (key: string) => string
): string {
	if (name === 'research_uzbek_law') return 'LexUz';
	if (name === 'create_document') return translate('Document creation');
	if (name === 'create_spreadsheet') return translate('Spreadsheet creation');
	if (name === 'research_prosecutor_orders') return translate('Prosecutor General’s orders');
	return name ?? '';
}
