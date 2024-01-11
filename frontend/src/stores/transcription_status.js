import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import axios from 'axios'

const Status = {
  LOADING: 'loading',
  WAITING_ON_USER_INPUT: 'waiting_on_user_input',
  CUTTING: 'cutting',
  UPLOADING: 'uploading',
  TRANSCRIBING: 'transcribing',
  TRANSCRIBED: 'transcribed',
  ERROR: 'error'
}

// create user store
const useTranscriptionStatusStore = defineStore('transcription_status', () => {
  const transcription_status = ref(Status.LOADING)
  const upload_progress = ref(0)

  // status
  const get_transcription_status = computed(() => transcription_status.value)

  const set_status = (status) => {
    transcription_status.value = status
  }

  // upload progress
  const get_upload_progress = computed(() => upload_progress.value)
  const set_upload_progress = (progress) => {
    upload_progress.value = progress
  }

  function load_transcript_in_progress() {
    return axios.get(`${import.meta.env.VITE_BACKEND_URL}/status`).then((response) => {
      if (response.data['transcription_in_progress'] === false) {
        transcription_status.value = Status.WAITING_ON_USER_INPUT
      } else {
        transcription_status.value = Status.TRANSCRIBING
      }
    })
  }

  return {
    get_transcription_status,
    set_status,
    load_transcript_in_progress,

    get_upload_progress,
    set_upload_progress
  }
})

export { useTranscriptionStatusStore, Status }
