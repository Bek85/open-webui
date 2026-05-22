import { readable } from 'svelte/store';

const TICK_INTERVAL_MS = 100;

let refCount = 0;
let intervalId: ReturnType<typeof setInterval> | null = null;
let visibilityBound = false;
let setNow: ((now: number) => void) | null = null;

function startTicker() {
	if (intervalId !== null) return;
	if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
	intervalId = setInterval(() => {
		setNow?.(Date.now());
	}, TICK_INTERVAL_MS);
}

function stopTicker() {
	if (intervalId !== null) {
		clearInterval(intervalId);
		intervalId = null;
	}
}

function handleVisibility() {
	if (typeof document === 'undefined') return;
	if (document.visibilityState === 'visible') {
		setNow?.(Date.now());
		if (refCount > 0) startTicker();
	} else {
		stopTicker();
	}
}

export const nowTick = readable<number>(Date.now(), (set) => {
	setNow = set;
	set(Date.now());
	if (typeof document !== 'undefined' && !visibilityBound) {
		document.addEventListener('visibilitychange', handleVisibility);
		visibilityBound = true;
	}
	return () => {
		// store has no subscribers — ensure ticker is off
		stopTicker();
	};
});

export function acquireTick() {
	refCount += 1;
	if (refCount === 1) startTicker();
}

export function releaseTick() {
	refCount = Math.max(0, refCount - 1);
	if (refCount === 0) stopTicker();
}
