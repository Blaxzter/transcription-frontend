<template>
  <div class="fill-height d-flex justify-center w-100">
    <div class="pa-10 fill-height d-flex flex-column w-100" style="max-width: 1200px">
      <div class="d-flex mb-10">
        <div class="component d-flex align-center">
          <v-icon class="mr-2" color="primary" size="48" style="vertical-align: middle">
            mdi-transcribe
          </v-icon>
          <h1>Transkribierungs Anwendung</h1>
        </div>
      </div>

      <TranscribeProgress />

      <TranscriptionCardList />
    </div>
  </div>
</template>

<script setup>
import TranscriptionCardList from '@/components/TranscriptionCardList.vue'
import TranscribeProgress from "@/components/TranscribeProgress.vue";
</script>

<style>

.component {
  margin: 1em;
  padding: 1em 2em;
  border-radius: 10px;
  background-color: rgba(255, 255, 255, 0.9);
}

.component-light {
  margin: 1em;
  padding: -0.5em 0.5em;
  border-radius: 10px;
  background-color: rgba(255, 255, 255, 0.3);
}
</style>
