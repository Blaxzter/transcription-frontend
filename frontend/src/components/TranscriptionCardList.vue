<script>
import TranscriptionCard from '@/components/TranscriptionCard.vue'
import { useTranscriptionsStore } from '@/stores/transcriptions'
import dayjs from 'dayjs'
import customParseFormat from 'dayjs/plugin/customParseFormat'
dayjs.extend(customParseFormat)

export default {
  name: 'TranscriptionCardList',
  components: {
    TranscriptionCard
  },
  data: () => ({
    transcription_store: useTranscriptionsStore(),
    transcripts_loading: true,
    sortOrder: 'newest' // 'newest' or 'oldest'
  }),
  mounted() {
    // get previous transcription_store
    this.transcription_store.load_transcriptions().then(() => {
      this.transcripts_loading = false
    })
  },
  methods: {
    toggleSortOrder() {
      this.sortOrder = this.sortOrder === 'newest' ? 'oldest' : 'newest'
    }
  },
  computed: {
    transcriptions() {
      const transcriptions = [...this.transcription_store.get_transcriptions]
      return transcriptions.sort((a, b) => {
        const dateA = dayjs(a.created_at, 'DD.MM.YYYY HH:mm:ss')
        const dateB = dayjs(b.created_at, 'DD.MM.YYYY HH:mm:ss')
        return this.sortOrder === 'newest' ? dateB - dateA : dateA - dateB
      })
    }
  }
}
</script>

<template>
  <div class="component-light">
    <div class="d-flex">
      <div class="component d-flex align-center">
        <v-icon class="mr-2" size="28" style="vertical-align: middle"> mdi-history</v-icon>
        <h2>Previous Transcriptions</h2>
      </div>
      <div class="flex-grow-1"></div>
      <v-btn
        @click="toggleSortOrder"
        variant="outlined"
        size="small"
        class="align-self-center mr-4"
      >
        <v-icon size="20" class="mr-1">
          {{ sortOrder === 'newest' ? 'mdi-sort-calendar-descending' : 'mdi-sort-calendar-ascending' }}
        </v-icon>
        {{ sortOrder === 'newest' ? 'Newest First' : 'Oldest First' }}
      </v-btn>
    </div>
    <div v-if="transcripts_loading">
      <div class="d-flex pa-8 justify-space-around align-center">
        <div>
          <v-progress-circular indeterminate size="32"></v-progress-circular>
          <span class="ms-5"> Laden... </span>
        </div>
      </div>
    </div>
    <div v-else>
      <div v-if="transcriptions.length" class="grid-container">
        <transcription-card
          v-for="transcription in transcriptions"
          :key="transcription.id"
          :transcription="transcription"
        ></transcription-card>
      </div>
      <div v-else class="d-flex pa-8 justify-space-around align-center">
        <div class="flex-grow-1"></div>
        <v-alert type="info" border="start" class="">
          Noch keine Transkriptionen vorhanden.
        </v-alert>
        <div class="flex-grow-1"></div>
      </div>
    </div>
  </div>
</template>

<style>
.grid-container {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  //grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  grid-gap: 1em;
  padding: 1em;
}
</style>
