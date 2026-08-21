import { marked } from 'marked';
import { describe, expect, it } from 'vitest';
import { neutralizeUnclosedStrong } from './streaming';

describe('neutralizeUnclosedStrong', () => {
	it('shows an unfinished strong span as plain streaming text', () => {
		expect(neutralizeUnclosedStrong('Intro **A long unfinished label')).toBe(
			'Intro A long unfinished label'
		);
	});

	it('keeps revealing a long label before its closing marker arrives', () => {
		const chunks = ['**', 'A long', ' bold label', ' keeps streaming', ' word by word'];
		let markdown = '';

		const rendered = chunks.map((chunk) => {
			markdown += chunk;
			return neutralizeUnclosedStrong(markdown);
		});

		expect(rendered).toEqual([
			'',
			'A long',
			'A long bold label',
			'A long bold label keeps streaming',
			'A long bold label keeps streaming word by word'
		]);
	});

	it('leaves balanced strong spans unchanged', () => {
		const markdown = 'Intro **A completed label** and body text.';
		expect(neutralizeUnclosedStrong(markdown)).toBe(markdown);
	});

	it('neutralizes only the final unmatched marker', () => {
		expect(neutralizeUnclosedStrong('**Complete** then **still streaming')).toBe(
			'**Complete** then still streaming'
		);
	});

	it('ignores escaped markers and markers inside code', () => {
		const markdown = '\\**literal marker and `**inline code`\n\n```md\n**fenced code\n```';
		expect(neutralizeUnclosedStrong(markdown)).toBe(markdown);
	});

	it('changes plain streaming text to strong only after the closer arrives', () => {
		const streamingTokens = marked.lexer(neutralizeUnclosedStrong('**Long streamed label'));
		const completeTokens = marked.lexer(neutralizeUnclosedStrong('**Long streamed label**'));

		expect(JSON.stringify(streamingTokens)).not.toContain('"type":"strong"');
		expect(JSON.stringify(completeTokens)).toContain('"type":"strong"');
	});
});
