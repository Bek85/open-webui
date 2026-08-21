/**
 * Remove the final unmatched `**` delimiter from the render-only copy of a
 * streaming response. This lets the unfinished label remain visible as plain
 * text until its closing delimiter arrives. The stored Markdown is never
 * changed, and completed strong spans pass through untouched.
 */
export const neutralizeUnclosedStrong = (markdown: string): string => {
	let unmatchedStrongIndex: number | null = null;
	let codeDelimiter: { character: '`' | '~'; length: number; block: boolean } | null = null;

	const isEscaped = (index: number) => {
		let backslashes = 0;
		for (let cursor = index - 1; cursor >= 0 && markdown[cursor] === '\\'; cursor--) {
			backslashes++;
		}
		return backslashes % 2 === 1;
	};

	const runLengthAt = (index: number, character: string) => {
		let cursor = index;
		while (markdown[cursor] === character) cursor++;
		return cursor - index;
	};

	const isFencePosition = (index: number) => {
		const lineStart = markdown.lastIndexOf('\n', index - 1) + 1;
		const prefix = markdown.slice(lineStart, index);
		return prefix.length <= 3 && /^ *$/.test(prefix);
	};

	for (let index = 0; index < markdown.length; index++) {
		const character = markdown[index];

		if (codeDelimiter) {
			if (character !== codeDelimiter.character || isEscaped(index)) continue;

			const runLength = runLengthAt(index, character);
			const closesDelimiter = codeDelimiter.block
				? isFencePosition(index) && runLength >= codeDelimiter.length
				: runLength === codeDelimiter.length;
			if (closesDelimiter) codeDelimiter = null;
			index += runLength - 1;
			continue;
		}

		if ((character === '`' || character === '~') && !isEscaped(index)) {
			const runLength = runLengthAt(index, character);
			const block = runLength >= 3 && isFencePosition(index);
			if (character === '`' || block) {
				codeDelimiter = { character, length: runLength, block };
				index += runLength - 1;
				continue;
			}
		}

		if (character === '*' && !isEscaped(index)) {
			const runLength = runLengthAt(index, character);
			if (runLength === 2) {
				unmatchedStrongIndex = unmatchedStrongIndex === null ? index : null;
			}
			index += runLength - 1;
		}
	}

	if (unmatchedStrongIndex === null) return markdown;
	return markdown.slice(0, unmatchedStrongIndex) + markdown.slice(unmatchedStrongIndex + 2);
};
