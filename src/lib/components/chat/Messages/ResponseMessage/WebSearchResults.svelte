<script lang="ts">
	import { getContext } from 'svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Collapsible from '$lib/components/common/Collapsible.svelte';
	import { fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';

	const i18n: any = getContext('i18n');

	type Item = {
		title?: string;
		link: string;
		date?: string;
		snippet?: string;
		score?: number;
		article?: string;
		document_type?: string;
	};
	type Status = {
		urls?: string[];
		items?: Item[];
		query?: string;
		count?: number;
		done?: boolean;
		[key: string]: unknown;
	};
	export let status: Status = { urls: [], query: '' };
	let state = false;

	function domainFor(link: string): string {
		try {
			return new URL(link).hostname.replace(/^www\./, '');
		} catch {
			return '';
		}
	}

	// Normalised string check: trims, drops empty / literal "None" / "null" sentinels
	// the pipeline sometimes emits for missing values.
	function cleanField(value: unknown): string {
		if (value === null || value === undefined) return '';
		const str = String(value).trim();
		if (!str) return '';
		const lower = str.toLowerCase();
		if (lower === 'none' || lower === 'null') return '';
		return str;
	}

	// Build the subtitle line. Order: article (formatted via i18n as "{n}-modda" /
	// "Art. {n}") OR document_type when there's no article, then date. Returns '' when
	// nothing useful is available so the row stays single-line instead of showing "Art. None".
	function subtitleFor(item: Item): string {
		const parts: string[] = [];
		const article = cleanField(item?.article);
		const docType = cleanField(item?.document_type);
		const date = cleanField(item?.date);
		if (article) {
			parts.push($i18n.t('{{article}}-modda', { article }));
		} else if (docType) {
			parts.push(docType);
		}
		if (date) parts.push(date);
		return parts.join(' · ');
	}
</script>

<Collapsible grow={true} className="w-full" buttonClassName="w-full" bind:open={state}>
	<div class="flex items-center gap-2 text-gray-500 transition">
		<slot />
		{#if state}
			<ChevronUp strokeWidth="2.5" className="size-3.5 " />
		{:else}
			<ChevronDown strokeWidth="2.5" className="size-3.5 " />
		{/if}
	</div>

	<div
		class="text-sm border border-gray-50 dark:border-gray-850/30 rounded-xl my-1.5 p-2 w-full"
		slot="content"
	>
		{#if status?.query}
			<a
				href="https://www.google.com/search?q={status.query}"
				target="_blank"
				class="flex w-full items-center p-1 px-3 group/item justify-between text-gray-800 dark:text-gray-300 font-normal! no-underline!"
			>
				<div class="flex gap-2 items-center">
					<Search />

					<div class=" line-clamp-1">
						{status.query}
					</div>
				</div>

				<div
					class=" ml-1 text-gray-400 dark:text-gray-300 group-hover/item:text-gray-700 dark:group-hover/item:text-white transition"
				>
					<!--  -->
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 16 16"
						fill="currentColor"
						class="size-4"
					>
						<path
							fill-rule="evenodd"
							d="M4.22 11.78a.75.75 0 0 1 0-1.06L9.44 5.5H5.75a.75.75 0 0 1 0-1.5h5.5a.75.75 0 0 1 .75.75v5.5a.75.75 0 0 1-1.5 0V6.56l-5.22 5.22a.75.75 0 0 1-1.06 0Z"
							clip-rule="evenodd"
						/>
					</svg>
				</div>
			</a>
		{/if}

		{#if status?.items}
			{#each status.items as item, itemIdx (item.link + itemIdx)}
				<a
					href={item.link}
					target="_blank"
					in:fly={{
						y: 4,
						duration: 220,
						delay: Math.min(itemIdx, 6) * 40,
						easing: cubicOut
					}}
					class="flex w-full items-center p-1 px-3 group/item justify-between text-gray-800 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg font-normal! no-underline! mb-1 min-w-0"
				>
					<div class="flex items-center gap-3 min-w-0 flex-1">
						<div class="shrink-0 dark:bg-white/95 dark:rounded-sm dark:p-px">
							<img
								src="https://www.google.com/s2/favicons?sz=32&domain={item.link}"
								alt="{item?.title ?? item.link} favicon"
								class="size-3.5"
							/>
						</div>

						<div class="min-w-0 flex flex-col">
							<div class="text-sm line-clamp-1">
								{item?.title ?? item.link}
							</div>
							{#if subtitleFor(item)}
								<div class="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">
									{subtitleFor(item)}
								</div>
							{/if}
						</div>
					</div>

					{#if domainFor(item.link)}
						<div
							class="ml-3 shrink-0 text-xs text-gray-500 dark:text-gray-500 truncate max-w-[40%] text-right"
						>
							{domainFor(item.link)}
						</div>
					{:else}
						<div
							class=" ml-1 text-gray-400 dark:text-gray-300 group-hover/item:text-gray-700 dark:group-hover/item:text-white transition"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="size-4"
							>
								<path
									fill-rule="evenodd"
									d="M4.22 11.78a.75.75 0 0 1 0-1.06L9.44 5.5H5.75a.75.75 0 0 1 0-1.5h5.5a.75.75 0 0 1 .75.75v5.5a.75.75 0 0 1-1.5 0V6.56l-5.22 5.22a.75.75 0 0 1-1.06 0Z"
									clip-rule="evenodd"
								/>
							</svg>
						</div>
					{/if}
				</a>
			{/each}
		{:else if status?.urls}
			{#each status.urls as url, urlIdx (url + urlIdx)}
				<a
					href={url}
					target="_blank"
					in:fly={{
						y: 4,
						duration: 220,
						delay: Math.min(urlIdx, 6) * 40,
						easing: cubicOut
					}}
					class="flex w-full items-center p-1 px-3 group/item justify-between text-gray-800 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg no-underline mb-1 min-w-0"
				>
					<div class="flex items-center gap-3 min-w-0 flex-1">
						<div class="shrink-0 dark:bg-white/95 dark:rounded-sm dark:p-px">
							<img
								src="https://www.google.com/s2/favicons?sz=32&domain={url}"
								alt="{url} favicon"
								class="size-3.5"
							/>
						</div>

						<div class="text-sm line-clamp-1 min-w-0">
							{url}
						</div>
					</div>

					{#if domainFor(url)}
						<div
							class="ml-3 shrink-0 text-xs text-gray-500 dark:text-gray-500 truncate max-w-[40%] text-right"
						>
							{domainFor(url)}
						</div>
					{:else}
						<div
							class=" ml-1 text-gray-400 dark:text-gray-300 group-hover/item:text-gray-700 dark:group-hover/item:text-white transition"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="size-4"
							>
								<path
									fill-rule="evenodd"
									d="M4.22 11.78a.75.75 0 0 1 0-1.06L9.44 5.5H5.75a.75.75 0 0 1 0-1.5h5.5a.75.75 0 0 1 .75.75v5.5a.75.75 0 0 1-1.5 0V6.56l-5.22 5.22a.75.75 0 0 1-1.06 0Z"
									clip-rule="evenodd"
								/>
							</svg>
						</div>
					{/if}
				</a>
			{/each}
		{/if}
	</div>
</Collapsible>
