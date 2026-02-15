<script setup>
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import WaveFormComponent from '@/components/WaveFormComponent.vue'
import { Status, useTranscriptionStatusStore } from '@/stores/transcription_status'
import { toast } from 'vue3-toastify'

const transcription_status = useTranscriptionStatusStore()
const { transcription_in_progress_id } = storeToRefs(transcription_status)
const files_model = ref([])

const selected_file = computed(() => {
  if (files_model.value.length === 0) return null
  return files_model.value[0]
})

const current_transcription_status = computed(() => {
  return transcription_status.get_transcription_status
})

const stopTranscription = async () => {
  const result = await transcription_status.stop_transcription()
  if (result) {
    toast.info('Transcription process has been stopped.')
  } else {
    toast.error('Failed to stop the transcription process.')
  }
}

onMounted(async () => {
  await transcription_status.load_transcript_in_progress()
})
</script>

<template>
  <div class="component mb-10">
    <div v-if="current_transcription_status === Status.LOADING">
      <div class="d-flex pa-8 justify-space-around align-center">
        <div>
          <v-progress-circular indeterminate size="32"></v-progress-circular>
          <span class="ms-5"> Lade Status.. </span>
        </div>
      </div>
    </div>
    <div
      v-else-if="
        current_transcription_status === Status.TRANSCRIBING && transcription_in_progress_id
      "
    >
      <div class="d-flex align-center mb-5">
        <h2>Transkription in Bearbeitung</h2>
        <div class="flex-grow-1"></div>
        <v-btn color="error" variant="tonal" prepend-icon="mdi-stop" @click="stopTranscription">
          Transkription stoppen
        </v-btn>
      </div>
      <WaveFormComponent :transcription_in_progress_id="transcription_in_progress_id" />
    </div>
    <div v-else-if="files_model.length === 0">
      <h2 class="mb-5">Lade hier neue Audio Datei hoch.</h2>

      <v-alert type="info" border="start" class="text-body-1 mb-5">
        Um eine neue Audio Datei hochzuladen, klicke auf das Feld unten und wähle eine Datei aus.
        <br />
        Du kannst die Datei auch per Drag and Drop in das Feld ziehen.
      </v-alert>

      <v-file-input
        v-model="files_model"
        show-size
        label="Lade eine Datei Hoch"
        accept=".mp3"
      ></v-file-input>
    </div>
    <div v-else>
      <div class="d-flex justify-end align-end">
        <v-tooltip text="Datei entfernen">
          <template v-slot:activator="{ props }">
            <v-btn
              v-bind="props"
              color="error"
              variant="text"
              icon="mdi-close"
              @click="files_model = []"
            >
            </v-btn>
          </template>
        </v-tooltip>
      </div>
      <WaveFormComponent :file="selected_file" />
    </div>
  </div>
</template>

<style scoped></style>
