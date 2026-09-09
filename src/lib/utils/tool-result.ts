// Tool execution finishing is not the same as the tool succeeding.
export function toolResultFailed(result: unknown): boolean {
	let value = result;
	for (let depth = 0; depth < 8 && typeof value === 'string'; depth++) {
		try {
			value = JSON.parse(value);
		} catch {
			return /^Error:/i.test(String(value).trim());
		}
	}
	return !!(value && typeof value === 'object' && 'error' in value && value.error);
}
