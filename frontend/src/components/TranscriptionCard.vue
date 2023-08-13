<template>
  <v-card @click="open">
    <v-card-title>
      <span class="headline">{{ transcription.transcription_name }}</span>
    </v-card-title>
    <v-card-text>
      {{ transcription.text }}
    </v-card-text>
  </v-card>
</template>

<script>
import router from "@/router";

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
  methods: {
    open() {
      router.push({ name: 'transcription', params: { transcription_id: this.transcription.id } })
    }
  }
}
</script>