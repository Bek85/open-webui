<script lang="ts">
	import { getContext } from 'svelte';
	import { scale } from 'svelte/transition';

	import WebSearchResults from '../WebSearchResults.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Check from '$lib/components/icons/Check.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';

	import { formatDuration, shouldShowDuration } from '$lib/utils/format-duration';
	import { nowTick } from '$lib/utils/timeline-tick';

	const i18n: any = getContext('i18n');

	export let status: any = null;
	export let done: boolean = false;

	// Translate known router notices, including those stored in existing chats.
	// Other reasoning descriptions are model content and must stay verbatim.
	const translatedNotices = new Set([
		'Routing to LexUz pipeline…',
		'Routing to Prosecutor pipeline…',
		'Researching legal sources…',
		'Preparing legal analysis…',
		'Legal analysis ready',
		'Legal research failed'
	]);
	$: reasoningDescription = translatedNotices.has(status?.description)
		? $i18n.t(status.description)
		: (status?.description ?? '');

	$: isDone =
		(done || status?.done) === true ||
		typeof status?.ended_at === 'number';

	$: durationMs = (() => {
		if (!status) return null;
		if (typeof status.duration_ms === 'number') return status.duration_ms;
		if (typeof status.started_at === 'number' && typeof status.ended_at === 'number') {
			return status.ended_at - status.started_at;
		}
		if (typeof status.started_at === 'number' && !isDone) {
			return Math.max(0, $nowTick - status.started_at);
		}
		return null;
	})();

	$: showDuration =
		status?.action !== 'thinking' &&
		status?.action !== 'summary' &&
		typeof durationMs === 'number' &&
		shouldShowDuration(durationMs);

	$: labelShimmer = !isDone;
</script>

{#if !status?.hidden}
	<div class="status-description flex items-center gap-2 py-0.5 w-full text-left">
		{#if status?.error}
			<span class="text-red-500 dark:text-red-400"><XMark className="size-4" /></span>
		{/if}
		{#if status?.action === 'web_search' && (status?.urls || status?.items)}
			<WebSearchResults {status}>
				<div class="flex flex-col justify-center -space-y-0.5 min-w-0 flex-1">
					<div
						class="{labelShimmer ? 'shimmer' : ''} text-base line-clamp-1 text-wrap"
					>
						<!-- $i18n.t("Generating search query") -->
						<!-- $i18n.t("No search query generated") -->
						<!-- $i18n.t('Searched {{count}} sites') -->
						{#if status?.description?.includes('{{count}}')}
							{$i18n.t(status?.description, {
								count: (status?.urls || status?.items).length
							})}
						{:else if status?.description === 'No search query generated'}
							{$i18n.t('No search query generated')}
						{:else if status?.description === 'Generating search query'}
							{$i18n.t('Generating search query')}
						{:else}
							{status?.description}
						{/if}
					</div>
				</div>
				{#if showDuration}
					<div class="ml-2 shrink-0 text-xs text-gray-500 tabular-nums">
						{formatDuration(durationMs ?? 0)}
					</div>
				{/if}
			</WebSearchResults>
		{:else if status?.action === 'knowledge_search' && (status?.items || status?.urls)}
			<WebSearchResults {status}>
				<div class="flex flex-col justify-center -space-y-0.5 min-w-0 flex-1">
					<div
						class="{labelShimmer
							? 'shimmer'
							: ''} text-base line-clamp-1 text-wrap"
					>
						{#if status?.query}
							{#if isDone && typeof status?.count === 'number'}
								{$i18n.t('Retrieved {{count}} results', { count: status.count })}
							{:else}
								{$i18n.t('Searching legal database for "{{query}}"', {
									query: status.query
								})}
							{/if}
						{:else if isDone}
							{$i18n.t('Retrieved {{count}} results', {
								count: (status?.items?.length ?? status?.urls?.length ?? 0)
							})}
						{:else}
							{$i18n.t('Searching legal database')}
						{/if}
					</div>
				</div>
				{#if showDuration}
					<div class="ml-2 shrink-0 text-xs text-gray-500 tabular-nums">
						{formatDuration(durationMs ?? 0)}
					</div>
				{/if}
			</WebSearchResults>
		{:else if status?.action === 'knowledge_search'}
			<div class="flex w-full items-center gap-2">
				<div class="flex flex-col justify-center -space-y-0.5 flex-1 min-w-0">
					<div
						class="{labelShimmer
							? 'shimmer'
							: ''} text-gray-500 dark:text-gray-500 text-base line-clamp-1 text-wrap"
					>
						{#if status?.query}
							{$i18n.t('Searching legal database for "{{query}}"', {
								query: status.query
							})}
						{:else}
							{$i18n.t('Searching legal database')}
						{/if}
					</div>
				</div>
				{#if showDuration}
					<div class="ml-2 shrink-0 text-xs text-gray-500 tabular-nums">
						{formatDuration(durationMs ?? 0)}
					</div>
				{/if}
			</div>
		{:else if status?.action === 'reasoning'}
			<div class="flex w-full items-start gap-2 min-w-0">
				<div
					class="{labelShimmer
						? 'shimmer'
						: ''} text-sm text-gray-700 dark:text-gray-300 leading-relaxed flex-1 min-w-0 markdown-prose-sm"
				>
					<Markdown id={`reasoning-${status?.started_at ?? ''}`} content={reasoningDescription} done={isDone} />
				</div>
				{#if showDuration}
					<div class="ml-2 mt-1 shrink-0 text-xs text-gray-500 tabular-nums">
						{formatDuration(durationMs ?? 0)}
					</div>
				{/if}
			</div>
		{:else if status?.action === 'summary'}
			<div class="flex w-full items-center gap-2 min-w-0">
				<div
					class="{labelShimmer
						? 'shimmer'
						: ''} text-base text-gray-700 dark:text-gray-200 line-clamp-1 flex-1 min-w-0"
				>
					{status?.description ?? $i18n.t('Legal research')}
				</div>
				{#if typeof durationMs === 'number' && durationMs >= 0}
					<div class="shrink-0 text-xs text-gray-500 tabular-nums">
						·&nbsp;{formatDuration(Math.max(durationMs, 100))}
					</div>
				{/if}
				{#if isDone && !status?.error}
					<div in:scale={{ start: 0.7, duration: 200 }} class="shrink-0 text-gray-500">
						<Check className="size-3.5" strokeWidth="2.5" />
					</div>
				{/if}
			</div>
		{:else if status?.action === 'thinking'}
			<div class="flex w-full items-center gap-2 min-w-0">
				<div
					class="shimmer text-sm text-gray-500 dark:text-gray-500 line-clamp-1 flex-1 min-w-0"
				>
					{status?.description ?? $i18n.t('Reasoning…')}
				</div>
			</div>
		{:else if status?.action === 'web_search_queries_generated' && status?.queries}
			<div class="flex w-full items-start gap-2">
				<div class="flex flex-col justify-center -space-y-0.5 flex-1 min-w-0">
					<div
						class="{labelShimmer
							? 'shimmer'
							: ''} text-gray-500 dark:text-gray-500 text-base line-clamp-1 text-wrap"
					>
						{$i18n.t(`Searching`)}
					</div>

					<div class=" flex gap-1 flex-wrap mt-2">
						{#each status.queries as query (query)}
							<div
								class="bg-gray-50 dark:bg-gray-850 flex rounded-lg py-1 px-2 items-center gap-1 text-xs"
							>
								<div>
									<Search className="size-3" />
								</div>

								<span class="line-clamp-1">
									{query}
								</span>
							</div>
						{/each}
					</div>
				</div>
				{#if showDuration}
					<div class="ml-2 mt-1 shrink-0 text-xs text-gray-500 tabular-nums">
						{formatDuration(durationMs ?? 0)}
					</div>
				{/if}
			</div>
		{:else if status?.action === 'queries_generated' && status?.queries}
			<div class="flex w-full items-start gap-2">
				<div class="flex flex-col justify-center -space-y-0.5 flex-1 min-w-0">
					<div
						class="{labelShimmer
							? 'shimmer'
							: ''} text-gray-500 dark:text-gray-500 text-base line-clamp-1 text-wrap"
					>
						{$i18n.t(`Querying`)}
					</div>

					<div class=" flex gap-1 flex-wrap mt-2">
						{#each status.queries as query (query)}
							<div
								class="bg-gray-50 dark:bg-gray-850 flex rounded-lg py-1 px-2 items-center gap-1 text-xs"
							>
								<div>
									<Search className="size-3" />
								</div>

								<span class="line-clamp-1">
									{query}
								</span>
							</div>
						{/each}
					</div>
				</div>
				{#if showDuration}
					<div class="ml-2 mt-1 shrink-0 text-xs text-gray-500 tabular-nums">
						{formatDuration(durationMs ?? 0)}
					</div>
				{/if}
			</div>
		{:else if status?.action === 'sources_retrieved' && status?.count !== undefined}
			<div class="flex w-full items-center gap-2">
				<div class="flex flex-col justify-center -space-y-0.5 flex-1 min-w-0">
					<div
						class="{labelShimmer
							? 'shimmer'
							: ''} text-gray-500 dark:text-gray-500 text-base line-clamp-1 text-wrap"
					>
						{#if status.count === 0}
							{$i18n.t('No sources found')}
						{:else if status.count === 1}
							{$i18n.t('Retrieved 1 source')}
						{:else}
							<!-- {$i18n.t('Source')} -->
							<!-- {$i18n.t('No source available')} -->
							<!-- {$i18n.t('No distance available')} -->
							<!-- {$i18n.t('Retrieved {{count}} sources')} -->
							{$i18n.t('Retrieved {{count}} sources', {
								count: status.count
							})}
						{/if}
					</div>
				</div>
				{#if showDuration}
					<div class="ml-2 shrink-0 text-xs text-gray-500 tabular-nums">
						{formatDuration(durationMs ?? 0)}
					</div>
				{/if}
			</div>
		{:else}
			<div class="flex w-full items-center gap-2">
				<div class="flex flex-col justify-center -space-y-0.5 flex-1 min-w-0">
					<div
						class="{labelShimmer
							? 'shimmer'
							: ''} text-gray-500 dark:text-gray-500 text-base line-clamp-1 text-wrap"
					>
						<!-- $i18n.t(`Searching "{{searchQuery}}"`) -->
						{#if status?.description?.includes('{{searchQuery}}')}
							{$i18n.t(status?.description, {
								searchQuery: status?.query
							})}
						{:else if status?.description === 'No search query generated'}
							{$i18n.t('No search query generated')}
						{:else if status?.description === 'Generating search query'}
							{$i18n.t('Generating search query')}
						{:else if status?.description === 'Searching the web'}
							{$i18n.t('Searching the web')}
						{:else}
							{status?.description}
						{/if}
					</div>
				</div>
				{#if showDuration}
					<div class="ml-2 shrink-0 text-xs text-gray-500 tabular-nums">
						{formatDuration(durationMs ?? 0)}
					</div>
				{/if}
			</div>
		{/if}
	</div>
{/if}
