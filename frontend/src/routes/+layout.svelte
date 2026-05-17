<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<nav class="border-b border-gray-200 bg-white">
	<div class="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
		<a href="/" class="text-sm font-semibold text-gray-900 hover:text-blue-600"> File Browser </a>
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
		<a href="/haystack" class="text-sm font-semibold text-gray-900 hover:text-blue-600">
			Haystack Node
		</a>
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
		<a href="/services" class="text-sm font-semibold text-gray-900 hover:text-blue-600">
			Services
		</a>
	</div>
</nav>
{@render children()}
