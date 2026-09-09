type Status = {
	research_id?: string;
	action?: string;
	started_at?: number;
	ended_at?: number;
	done?: boolean;
	[key: string]: unknown;
};

export function statusKey(status: Status): string | null {
	return typeof status.started_at === 'number'
		? `${status.research_id ?? ''}#${status.action ?? ''}#${status.started_at}`
		: null;
}

export function currentResearchStatus(history: Status[]): Status | null {
	// Concurrent research calls can finish out of order. Keep pending work visible.
	const research = history.filter((s) => s.research_id);
	const pending = research.filter((s) => s.done === false && typeof s.ended_at !== 'number');
	if (pending.length) return pending.at(-1) ?? null;
	if (!history.at(-1)?.research_id) return history.at(-1) ?? null;
	if (research.length) {
		return research.reduce((latest, s) =>
			(s.ended_at ?? s.started_at ?? 0) >= (latest.ended_at ?? latest.started_at ?? 0) ? s : latest
		);
	}
	return history.at(-1) ?? null;
}
