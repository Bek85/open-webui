export function formatDuration(ms: number): string {
	if (!Number.isFinite(ms) || ms < 0) return '';
	const totalSeconds = ms / 1000;

	if (totalSeconds < 60) {
		const seconds = Math.max(0.1, totalSeconds);
		return `${seconds.toFixed(1)}s`;
	}

	if (totalSeconds < 3600) {
		const minutes = Math.floor(totalSeconds / 60);
		const seconds = Math.round(totalSeconds - minutes * 60);
		return `${minutes}m ${String(seconds).padStart(2, '0')}s`;
	}

	const hours = Math.floor(totalSeconds / 3600);
	const minutes = Math.round((totalSeconds - hours * 3600) / 60);
	return `${hours}h ${String(minutes).padStart(2, '0')}m`;
}

export function shouldShowDuration(ms: number): boolean {
	return Number.isFinite(ms) && ms >= 50;
}
