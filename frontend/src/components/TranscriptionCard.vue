<template>
  <v-card @click="open" class="transcription--card d-flex flex-column">
    <v-card-title>
      <span class="headline">{{ transcription.transcription_name }}</span>
    </v-card-title>
    <v-card-text class="flex-grow-1">
      {{ transcription_text }}
    </v-card-text>
    <v-card-actions>
      <v-icon size="16" class="mr-2">mdi-clock-time-four-outline</v-icon>
      vom {{ transcription_time }}
    </v-card-actions>
  </v-card>
</template>

<script>
import router from "@/router";
import customParseFormat from 'dayjs/plugin/customParseFormat'
import dayjs from "dayjs";
dayjs.extend(customParseFormat)

export default {
  name: 'TranscriptionCard',
  props: {
    transcription: {
      type: Object,
      required: true
    }
  },
  mounted() {

  },
  computed: {
    transcription_text() {
      return this.transcription.text.substring(0, 100) + '...'
    },
    transcription_time() {
      return dayjs(this.transcription.created_at, 'DD.MM.YYYY HH:mm:ss').format('DD.MM.YY HH:mm')
    }
  },
  methods: {
    open() {
      router.push({ name: 'transcription', params: { transcription_id: this.transcription.id } })
    }
  }
}
</script>

<style>
.transcription--card {
  cursor: pointer;
}

.transcription--card:hover {
  background-color: #f5f5f5;
  border-radius: 4px;
  box-shadow: 0 2px 4px 0 rgba(0,0,0,0.2);

}
</style>