<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import { fly, slide, scale } from 'svelte/transition';
	import { cubicOut, cubicInOut } from 'svelte/easing';

	import StatusItem from './StatusHistory/StatusItem.svelte';
	import Check from '$lib/components/icons/Check.svelte';

	import { formatDuration } from '$lib/utils/format-duration';
	import { acquireTick, releaseTick, nowTick } from '$lib/utils/timeline-tick';

	const i18n: any = getContext('i18n');

	export let statusHistory: any[] = [];
	export let expand: boolean = false;

	let showHistory = true;

	$: if (expand) {
		showHistory = true;
	} else {
		showHistory = false;
	}

	let history: any[] = [];
	let status: any = null;

	$: if (history && history.length > 0) {
		status = history.at(-1);
	}

	function dedupeHistory(arr: any[] = []) {
		// Pipelines re-emit the same step (e.g. done:false then done:true) carrying the same
		// `started_at`. Without deduping, two entries share a key and Svelte's keyed `{#each}`
		// crashes ("duplicate keys"). Keep only the latest emit per (action, started_at).
		// Also drop content-less events (no action, no description, no payload) — those
		// render as orphan dots with no text and look broken.
		if (!arr || arr.length === 0) return [];
		const seen = new Map<string, number>();
		const result: any[] = [];
		for (const item of arr) {
			if (!item) continue;
			const hasContent =
				item.action ||
				(item.description && String(item.description).trim() !== '') ||
				item.query ||
				(Array.isArray(item.items) && item.items.length > 0) ||
				(Array.isArray(item.urls) && item.urls.length > 0) ||
				item.count != null ||
				(Array.isArray(item.queries) && item.queries.length > 0);
			if (!hasContent) continue;
			const key =
				typeof item.started_at === 'number'
					? `${item.action ?? ''}#${item.started_at}`
					: null;
			if (key !== null && seen.has(key)) {
				result[seen.get(key) as number] = item;
			} else {
				if (key !== null) seen.set(key, result.length);
				result.push(item);
			}
		}
		return result;
	}

	$: if (JSON.stringify(statusHistory) !== JSON.stringify(history)) {
		history = dedupeHistory(statusHistory);
	}

	$: inFlightCount = (history ?? []).filter(
		(s) => s && s.done === false && typeof s.ended_at !== 'number'
	).length;

	let ticking = false;
	$: if (inFlightCount > 0 && !ticking) {
		acquireTick();
		ticking = true;
	} else if (inFlightCount === 0 && ticking) {
		releaseTick();
		ticking = false;
	}

	onDestroy(() => {
		if (ticking) {
			releaseTick();
			ticking = false;
		}
	});

	$: isSummary = status?.action === 'summary';
	$: summaryDone = isSummary && (status?.done === true || typeof status?.ended_at === 'number');

	$: firstStarted = (history ?? [])
		.map((s) => s?.started_at)
		.find((t) => typeof t === 'number');

	$: lastEnded = [...(history ?? [])]
		.reverse()
		.map((s) => s?.ended_at)
		.find((t) => typeof t === 'number');

	$: totalDurationMs = (() => {
		if (typeof status?.duration_ms === 'number') return status.duration_ms;
		if (
			typeof status?.started_at === 'number' &&
			typeof status?.ended_at === 'number'
		) {
			return status.ended_at - status.started_at;
		}
		if (typeof firstStarted === 'number') {
			if (typeof lastEnded === 'number' && inFlightCount === 0) {
				return lastEnded - firstStarted;
			}
			return Math.max(0, $nowTick - firstStarted);
		}
		return null;
	})();

	// Idle "thinking" placeholder
	const IDLE_THINKING_MS = 600;
	let idleTimer: ReturnType<typeof setTimeout> | null = null;
	let showIdleThinking = false;

	function clearIdleTimer() {
		if (idleTimer !== null) {
			clearTimeout(idleTimer);
			idleTimer = null;
		}
	}

	$: {
		// Recompute on history change
		void history;
		clearIdleTimer();
		showIdleThinking = false;
		const last = history?.at(-1);
		const lastDone =
			last && (last.done === true || typeof last.ended_at === 'number');
		const stillWaitingForAnswer = expand === true; // parent passes expand=true while message.content==='';
		if (lastDone && stillWaitingForAnswer && last?.action !== 'summary') {
			idleTimer = setTimeout(() => {
				showIdleThinking = true;
				idleTimer = null;
			}, IDLE_THINKING_MS);
		}
	}

	onDestroy(() => clearIdleTimer());

	$: timelineItems = (history ?? []).slice(0, -1);
</script>

{#if history && history.length > 0}
	{#if status?.hidden !== true}
		<div class="text-sm flex flex-col w-full">
			{#if showHistory}
				<div
					class="flex flex-row"
					transition:slide={{ duration: 320, easing: cubicInOut }}
				>
					{#if history.length > 1 || showIdleThinking}
						<div class="w-full">
							{#each timelineItems as item, idx (typeof item?.started_at === 'number' ? `${item.action ?? ''}#${item.started_at}` : `idx#${idx}`)}
								<div
									class="flex items-stretch gap-2 mb-1"
									in:fly={{ y: 6, duration: 220, easing: cubicOut }}
								>
									<div class=" ">
										<div class="pt-3 px-1 mb-1.5">
											<span
												class="relative flex size-1.5 rounded-full justify-center items-center"
											>
												<span
													class="relative inline-flex size-1.5 rounded-full bg-gray-500 dark:bg-gray-300"
												></span>
											</span>
										</div>

										<div
											class="w-px ml-[6px] h-[calc(100%-14px)] bg-gray-300 dark:bg-white/20"
										/>
									</div>

									<StatusItem status={item} done={true} />
								</div>
							{/each}

							{#if showIdleThinking}
								<div
									class="flex items-stretch gap-2 mb-1"
									in:fly={{ y: 6, duration: 220, easing: cubicOut }}
								>
									<div class=" ">
										<div class="pt-3 px-1 mb-1.5">
											<span
												class="relative flex size-1.5 rounded-full justify-center items-center"
											>
												<span
													class="absolute inline-flex h-full w-full animate-ping rounded-full bg-gray-500 dark:bg-gray-300 opacity-75"
												></span>
												<span
													class="relative inline-flex size-1.5 rounded-full bg-gray-500 dark:bg-gray-300 animate-breathing"
												></span>
											</span>
										</div>
										<div
											class="w-px ml-[6px] h-[calc(100%-14px)] bg-gray-300 dark:bg-white/20"
										/>
									</div>
									<StatusItem
										status={{ action: 'thinking', done: false, description: $i18n.t('Reasoning…') }}
									/>
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{/if}

			<button
				class="w-full text-left"
				on:click={() => {
					showHistory = !showHistory;
				}}
			>
				<div class="flex items-start gap-2">
					{#if history.length > 1}
						<div class="pt-3 px-1">
							<span class="relative flex size-1.5 rounded-full justify-center items-center">
								{#if status?.done === false && typeof status?.ended_at !== 'number'}
									<span
										class="absolute inline-flex h-full w-full animate-ping rounded-full bg-gray-500 dark:bg-gray-300 opacity-75"
									></span>
									<span
										class="relative inline-flex size-1.5 rounded-full bg-gray-500 dark:bg-gray-300 animate-breathing"
									></span>
								{:else if summaryDone}
									<span
										in:scale={{ start: 0.6, duration: 200 }}
										class="relative inline-flex size-1.5 rounded-full bg-gray-500 dark:bg-gray-300"
									></span>
								{:else}
									<span
										class="relative inline-flex size-1.5 rounded-full bg-gray-500 dark:bg-gray-300"
									></span>
								{/if}
							</span>
						</div>
					{/if}

					<div class="flex-1 min-w-0">
						<StatusItem {status} />

						{#if isSummary && summaryDone && history.length > 1}
							<div class="mt-1 flex items-center gap-1 text-xs text-gray-500">
								<span>{showHistory ? $i18n.t('Show less') : $i18n.t('Show more')}</span>
								{#if totalDurationMs !== null && totalDurationMs >= 0}
									<span aria-hidden="true">·</span>
									<span class="tabular-nums">
										{formatDuration(Math.max(totalDurationMs ?? 0, 100))}
									</span>
								{/if}
								<span aria-hidden="true">·</span>
								<span class="flex items-center gap-0.5">
									<Check className="size-3" strokeWidth="2.5" />
									{$i18n.t('Done')}
								</span>
							</div>
						{/if}
					</div>
				</div>
			</button>
		</div>
	{/if}
{/if}
