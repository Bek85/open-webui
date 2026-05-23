<script lang="ts">
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Collapsible from '$lib/components/common/Collapsible.svelte';
	import { fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';

	type Item = { title?: string; link: string; date?: string; snippet?: string; score?: number };
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
		class="text-sm border border-gray-50 dark:border-gray-850 rounded-xl my-1.5 p-2 w-full"
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
					class=" ml-1 text-white dark:text-gray-900 group-hover/item:text-gray-600 dark:group-hover/item:text-white transition"
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
								alt="favicon"
								class="size-3.5"
							/>
						</div>

						<div class="text-sm line-clamp-1 min-w-0">
							{#if item?.date}<span class="text-gray-500 mr-1">{item.date}</span>{/if}{item?.title ??
								item.link}
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
							class=" ml-1 text-white dark:text-gray-900 group-hover/item:text-gray-600 dark:group-hover/item:text-white transition"
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
								alt="favicon"
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
							class=" ml-1 text-white dark:text-gray-900 group-hover/item:text-gray-600 dark:group-hover/item:text-white transition"
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
