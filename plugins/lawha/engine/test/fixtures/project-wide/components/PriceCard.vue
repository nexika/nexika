<script setup lang="ts">
defineProps<{ title: string; price?: number }>()
</script>

<template>
  <div class="ml-4 rounded-lg" style="color: #ff0000">{{ title }}</div>
</template>
