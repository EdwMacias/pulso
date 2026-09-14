<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useSession } from './stores/session'
import { router } from './router'
const expire = () => { useSession().user = null; if (router.currentRoute.value.meta.authenticated) router.push('/login') }
onMounted(() => window.addEventListener('session-expired', expire))
onUnmounted(() => window.removeEventListener('session-expired', expire))
</script>
<template><RouterView /></template>
