<script lang="ts">
	import { getWorkspaceCaption } from '$lib/utils/tool-names';
	import { toast } from 'svelte-sonner';
	import { marked } from 'marked';

	import { onMount, getContext, tick, createEventDispatcher } from 'svelte';
	import { blur, fade } from 'svelte/transition';

	const dispatch = createEventDispatcher();

	import { updateFolderById } from '$lib/apis/folders';

	import {
		config,
		user,
		models as _models,
		temporaryChatEnabled,
		selectedFolder
	} from '$lib/stores';
	import { refreshChatList } from '$lib/stores/chatList';
	import { sanitizeResponseContent, extractCurlyBraceWords } from '$lib/utils';
	import { WEBUI_BASE_URL } from '$lib/constants';

	import Suggestions from './Suggestions.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte';
	import MessageInput from './MessageInput.svelte';
	import FolderPlaceholder from './Placeholder/FolderPlaceholder.svelte';
	import FolderTitle from './Placeholder/FolderTitle.svelte';

	const i18n = getContext('i18n');

	export let createMessagePair: Function;
	export let stopResponse: Function;

	export let autoScroll = false;

	export let atSelectedModel: Model | undefined;
	export let selectedModels: [''];

	export let history;

	export let prompt = '';
	export let files = [];
	export let messageInput = null;

	export let selectedToolIds = [];
	export let selectedSkillIds = [];
	export let selectedFilterIds = [];
	export let pendingOAuthTools = [];
	export let onUpload: Function = (e) => {};
	export let dragged = false;

	export let showCommands = false;

	export let imageGenerationEnabled = false;
	export let codeInterpreterEnabled = false;
	export let webSearchEnabled = false;

	export let onSelect = (e) => {};
	export let onChange = (e) => {};
	export let onWebSearchToggle: Function = () => {};

	export let toolServers = [];

	let models = [];
	let selectedModelIdx = 0;

	$: if (selectedModels.length > 0) {
		selectedModelIdx = models.length - 1;
	}

	$: models = selectedModels.map((id) => $_models.find((m) => m.id === id));

	// True when viewing a shared folder the current user doesn't own AND lacks write access
	$: folderReadOnly =
		$selectedFolder != null &&
		$selectedFolder.user_id !== $user?.id &&
		$selectedFolder.permission !== 'write';
</script>

<div class="m-auto w-full max-w-[58rem] px-2 @2xl:px-20 translate-y-6 py-24 text-center">
	{#if $temporaryChatEnabled}
		<Tooltip
			content={$i18n.t("This chat won't appear in history and your messages will not be saved.")}
			className="w-full flex justify-center mb-0.5"
			placement="top"
		>
			<div class="flex items-center gap-1.5 text-gray-500 text-xs my-1 w-fit">
				<EyeSlash strokeWidth="2" className="size-3.5" />{$i18n.t('Temporary Chat')}
			</div>
		</Tooltip>
	{/if}

	<div class="w-full text-3xl text-gray-800 dark:text-gray-100 text-center flex items-center gap-4">
		<div class="w-full flex flex-col justify-center items-center">
			{#if $selectedFolder}
				<FolderTitle
					folder={$selectedFolder}
					readOnly={folderReadOnly}
					onUpdate={async (folder) => {
						await refreshChatList(localStorage.token);
					}}
					onDelete={async () => {
						await refreshChatList(localStorage.token);

						selectedFolder.set(null);
					}}
				/>
			{:else}
				<div class="flex flex-row justify-center gap-3 @sm:gap-3.5 w-fit px-5 max-w-xl">
					<div class="flex shrink-0 justify-center">
						<div class="flex -space-x-4 mb-0.5" in:fade={{ duration: 100 }}>
							{#each models as model, modelIdx}
								<Tooltip
									content={(models[modelIdx]?.info?.meta?.tags ?? [])
										.map((tag) => tag.name.toUpperCase())
										.join(', ')}
									placement="top"
								>
									<button
										aria-hidden={models.length <= 1}
										aria-label={$i18n.t('Get information on {{name}} in the UI', {
											name: models[modelIdx]?.name
										})}
										on:click={() => {
											selectedModelIdx = modelIdx;
										}}
									>
										<!--																				<img-->
										<!--																					crossorigin="anonymous"-->
										<!--																					src={model?.info?.meta?.profile_image_url ??-->
										<!--																						($i18n.language === 'dg-DG'-->
										<!--																							? `${WEBUI_BASE_URL}/doge.png`-->
										<!--																							: `${WEBUI_BASE_URL}/static/pro_dark.gif`)}-->
										<!--																					class="w-150 h-auto @sm:w-150 rounded-full border-[1px] border-gray-100 dark:border-none"-->
										<!--																					aria-hidden="true"-->
										<!--																					draggable="false"-->
										<!--																				/>-->

										<!--										urldan rasm kelishi shart bo'yicha rasmni chiqarish-->
										<!--										<img-->
										<!--											crossorigin='anonymous'-->
										<!--											src={-->
										<!--													model?.info?.meta?.profile_image_url ??-->
										<!--													($i18n.language === 'dg-DG'-->
										<!--														? `${WEBUI_BASE_URL}/doge.png`-->
										<!--														: model?.id === 'lexuz_pipeline' // <&#45;&#45; model ID yoki nomiga qarab-->
										<!--															? `${WEBUI_BASE_URL}/static/lex_dark.gif`-->
										<!--															: `${WEBUI_BASE_URL}/static/pro_dark.gif`)-->
										<!--												}-->
										<!--											class='w-150 h-auto @sm:w-150 rounded-full border-[1px] border-gray-100 dark:border-none'-->
										<!--											aria-hidden='true'-->
										<!--											draggable='false'-->
										<!--										/>-->

										<img
											crossorigin="anonymous"
											src={`${WEBUI_BASE_URL}/static/${model?.id === 'lexuz_pipeline' ? 'lex_dark.gif' : 'pro_dark.gif'}`}
											class="w-150 h-auto @sm:w-150 rounded-full border-none border-gray-100 dark:border-none"
											aria-hidden="true"
											draggable="false"
										/>
									</button>
								</Tooltip>
							{/each}
						</div>
					</div>

					<!--					<div-->
					<!--						class=" text-3xl @sm:text-3xl line-clamp-1 flex items-center"-->
					<!--						in:fade={{ duration: 100 }}-->
					<!--					>-->
					<!--						{#if models[selectedModelIdx]?.name}-->
					<!--							<Tooltip-->
					<!--								content={models[selectedModelIdx]?.name}-->
					<!--								placement="top"-->
					<!--								className=" flex items-center "-->
					<!--							>-->
					<!--								<span class="line-clamp-1">-->
					<!--									{models[selectedModelIdx]?.name}-->
					<!--								</span>-->
					<!--							</Tooltip>-->
					<!--						{:else}-->
					<!--							{$i18n.t('Hello, {{name}}', { name: $user?.name })}-->
					<!--						{/if}-->
					<!--					</div>-->

				</div>

				<div class="flex mt-1 mb-2">
					<div in:fade={{ duration: 100, delay: 50 }}>
						{#if models[selectedModelIdx]?.info?.meta?.description ?? null}
							<Tooltip
								className=" w-fit"
								content={marked.parse(
									sanitizeResponseContent(
										getWorkspaceCaption(models[selectedModelIdx]?.info?.meta?.description ?? '', $i18n.t)
									).replaceAll('\n', '<br>')
								)}
								placement="top"
							>
								<div
									class="mt-0.5 px-2 text-sm font-normal text-gray-500 dark:text-gray-400 line-clamp-2 max-w-xl markdown"
								>
									{@html marked.parse(
										sanitizeResponseContent(
										getWorkspaceCaption(models[selectedModelIdx]?.info?.meta?.description ?? '', $i18n.t)
									).replaceAll('\n', '<br>')
									)}
								</div>
							</Tooltip>

							{#if models[selectedModelIdx]?.info?.meta?.user}
								<div class="mt-0.5 text-sm font-normal text-gray-400 dark:text-gray-500">
									By
									{#if models[selectedModelIdx]?.info?.meta?.user.community}
										<a
											href="https://openwebui.com/m/{models[selectedModelIdx]?.info?.meta?.user
												.username}"
											>{models[selectedModelIdx]?.info?.meta?.user.name
												? models[selectedModelIdx]?.info?.meta?.user.name
												: `@${models[selectedModelIdx]?.info?.meta?.user.username}`}</a
										>
									{:else}
										{models[selectedModelIdx]?.info?.meta?.user.name}
									{/if}
								</div>
							{/if}
						{/if}
					</div>
				</div>
			{/if}

			<div class="text-base font-normal @md:max-w-3xl w-full py-3 {atSelectedModel ? 'mt-2' : ''}">
				{#if !($selectedFolder && folderReadOnly)}
					<MessageInput
						bind:this={messageInput}
						{history}
						bind:selectedModels
						bind:files
						bind:prompt
						bind:autoScroll
						bind:selectedToolIds
						bind:selectedSkillIds
						bind:selectedFilterIds
						bind:imageGenerationEnabled
						bind:codeInterpreterEnabled
						bind:webSearchEnabled
						bind:atSelectedModel
						bind:showCommands
						bind:dragged
						{pendingOAuthTools}
						{toolServers}
						{stopResponse}
						{createMessagePair}
						placeholder={$i18n.t('How can I help you today?')}
						{onChange}
						{onUpload}
						{onWebSearchToggle}
						on:chatVariables
						on:submit={(e) => {
							dispatch('submit', e.detail);
						}}
					/>
				{/if}
			</div>
		</div>
	</div>

	{#if $selectedFolder}
		<div class="mx-auto px-4 md:max-w-3xl md:px-6 min-h-62" in:fade={{ duration: 200, delay: 200 }}>
			<FolderPlaceholder folder={$selectedFolder} />
		</div>
	{:else}
		<div class="mx-auto max-w-2xl mt-2" in:fade={{ duration: 200, delay: 200 }}>
			<div class="mx-5">
				<Suggestions
					suggestionPrompts={atSelectedModel?.info?.meta?.suggestion_prompts ??
						models[selectedModelIdx]?.info?.meta?.suggestion_prompts ??
						$config?.default_prompt_suggestions ??
						[]}
					inputValue={prompt}
					{onSelect}
				/>
			</div>
		</div>
	{/if}
</div>
