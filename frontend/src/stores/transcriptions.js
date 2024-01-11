import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import axios from "axios";

// create user store
export const useTranscriptionsStore = defineStore('transcriptions',  () => {
  const transcriptions = ref([])

  // getters
  const get_transcriptions = computed(() => transcriptions.value)

  function add_transcription(new_transcription) {
    transcriptions.value.push(new_transcription)
  }

  function load_transcriptions() {
    return axios.get(`${import.meta.env.VITE_BACKEND_URL}/transcriptions`).then((response) => {
      transcriptions.value = response.data
    })
  }

  return {
    get_transcriptions,
    add_transcription,
    load_transcriptions
  }
})
