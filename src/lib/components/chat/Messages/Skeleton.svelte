<script lang="ts">
	export let size = 'md';
</script>

<div class="flex items-center {size === 'md' ? 'my-2' : 'my-1'} mx-1">
	<!-- Three dots animation -->
	<div class="flex items-center space-x-1">
		<div class="dot-1 w-2 h-2 bg-gray-600 dark:bg-gray-300 rounded-full"></div>
		<div class="dot-2 w-2 h-2 bg-gray-600 dark:bg-gray-300 rounded-full"></div>
		<div class="dot-3 w-2 h-2 bg-gray-600 dark:bg-gray-300 rounded-full"></div>
	</div>
</div>

<style>
	@keyframes dotPulse {
		0%,
		80%,
		100% {
			transform: scale(0.8);
			opacity: 0.5;
		}
		40% {
			transform: scale(1);
			opacity: 1;
		}
	}

	.dot-1 {
		animation: dotPulse 1.4s ease-in-out infinite;
		animation-delay: 0s;
	}

	.dot-2 {
		animation: dotPulse 1.4s ease-in-out infinite;
		animation-delay: 0.2s;
	}

	.dot-3 {
		animation: dotPulse 1.4s ease-in-out infinite;
		animation-delay: 0.4s;
	}

	@keyframes thinkingDots {
		0%,
		20% {
			color: transparent;
		}
		50% {
			color: currentColor;
		}
		100% {
			color: transparent;
		}
	}

	.thinking-dots {
		animation: thinkingDots 1.5s ease-in-out infinite;
	}

	.thinking-text {
		display: flex;
		align-items: center;
	}
</style>
