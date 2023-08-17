<template>
  <v-container :fluid="true">
    <div class="d-flex mb-2 w-100">
      <div class="component d-flex align-center">
        <v-icon class="mr-2" color="primary" size="48" style="vertical-align: middle">
          mdi-transcribe
        </v-icon>
        <h1>{{ transcription?.file_name }}</h1>
      </div>
      <div class="flex-grow-1"></div>
      <div class="component text-h6">Vom: {{ transcription?.created_at }}</div>
    </div>

    <div class="w-100">
      <div class="component">
        <WaveFormComponent
          v-if="file || audio_url"
          :file="file"
          :url="audio_url"
          :only_view="true"
        />
        <div v-else>
          <v-progress-linear indeterminate color="green" height="12"></v-progress-linear>
        </div>
      </div>
    </div>

    <div class="w-100">
      <div class="component">
        <div class="d-flex align-center">
          <div class="text-h5">Transkribierter Text</div>
          <div class="flex-grow-1"></div>
          <v-btn
            icon="mdi-content-copy"
            variant="text"
            color="success"
            @click="copy_content"
          ></v-btn>
          <v-btn
            icon="mdi-delete"
            variant="text"
            color="error"
            @click="delete_dialog = true"
          ></v-btn>
        </div>
        <div>
          <span v-for="(chunk, idx) in transcription?.chunks" :key="idx">
            {{ chunk.text }}
          </span>
        </div>
      </div>
    </div>
  </v-container>

  <v-dialog v-model="delete_dialog" max-width="500px">
    <v-card>
      <v-card-title class="headline">Transkription löschen</v-card-title>
      <v-card-text>Wollen Sie die Transkription wirklich löschen?</v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn
          color="success"
          varient="flat"
          @click="delete_dialog = false"
          prepend-icon="mdi-window-close"
          >Abbrechen
        </v-btn>
        <v-btn color="error" varient="tonal" @click="delete_transcription" prepend-icon="mdi-delete">Löschen</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import axios from 'axios'
import { useUserStore } from '@/stores/user'
import WaveFormComponent from '@/components/WaveFormComponent.vue'
import router from "@/router";
import {toast} from "vue3-toastify";

export default {
  name: 'TranscriptionView',
  components: { WaveFormComponent },
  data: () => ({
    user: useUserStore(),
    transcription: undefined,
    file: undefined,
    delete_dialog: false
  }),
  props: {
    transcription_id: {
      type: String,
      required: true
    }
  },
  mounted() {
    this.file = this.user.get_user_file
    console.log(this.file)
    axios
      .get(`${import.meta.env.VITE_BACKEND_URL}/transcriptions/${this.transcription_id}`)
      .then((response) => {
        this.transcription = response.data
      }).catch((error) => {
        console.log(error)
        router.push({ name: 'home' })
        toast.error("Transkription konnte nicht geladen werden")
      })
  },
  computed: {
    audio_url() {
      return `${import.meta.env.VITE_BACKEND_URL}/audio/${this.transcription_id}`
    }
  },
  methods: {
    async delete_transcription() {
      await axios.delete(
        `${import.meta.env.VITE_BACKEND_URL}/transcriptions/${this.transcription_id}`,
      ).then(() => {
        router.push({ name: 'home' })
        toast.info("Transkription wurde erfolgreich gelöscht")
      })
    },
    copy_content() {
      navigator.clipboard.writeText(this.transcription?.text)
      toast.success("Text wurde erfolgreich in die ablage Kopiert"); // ToastOptions
    }
  }
}
</script>
