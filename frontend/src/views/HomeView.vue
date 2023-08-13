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

        <div class="flex-grow-1"></div>
        <div class="component d-flex align-center">
          <span class="text-body-1"> Transkribierungs Server Status: </span>
          <v-progress-circular
            v-if="server_status_loading"
            indeterminate
            size="24"
            class="ml-2"></v-progress-circular>
          <v-icon v-else-if="serverStatus" class="ml-2" color="success" size="24">mdi-check</v-icon>
          <v-icon v-else class="ml-2" color="error" size="24"> mdi-close</v-icon>
        </div>
      </div>

      <div class="component mb-10">
<!--        <div v-if="serverStatus">-->
        <div>

          <div v-if="files_model.length === 0">
            <h2 class="mb-5">Lade hier neue Audio Datei hoch.</h2>

            <v-alert type="info" border="start" class="text-body-1 mb-5">
              Um eine neue Audio Datei hochzuladen, klicke auf das Feld unten und wähle eine Datei
              aus.
              <br />
              Du kannst die Datei auch per Drag and Drop in das Feld ziehen.
            </v-alert>

            <v-file-input
                v-model="files_model"
                show-size
                label="Lade eine Datei Hoch"
                accept="audio/*"
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
            <WaveFormComponent :file="selected_file" @transcription_created="transcriptions.push($event)" />
          </div>
        </div>
<!--        <div v-else>-->
<!--          <v-alert type="warning" border="start" class="text-body-1 mb-5">-->
<!--            Der Transcribierungs Server ist grade ausgeschaltet.-->
<!--          </v-alert>-->

<!--          <v-btn-->
<!--            color="primary"-->
<!--            class="w-100"-->
<!--            size="50"-->
<!--            variant="outlined"-->
<!--            @click="server_starting"-->
<!--          >-->
<!--            <v-icon class="me-5" size="30"> mdi-rocket</v-icon>-->
<!--            Starte den Transcribierungs Server-->
<!--          </v-btn>-->
<!--        </div>-->
      </div>

      <div class="component-light">
        <div class="d-flex">
          <div class="component d-flex align-center">
            <v-icon class="mr-2" size="28" style="vertical-align: middle"> mdi-history</v-icon>
            <h2>Previous Transcriptions</h2>
          </div>
          <div class="flex-grow-1"></div>
        </div>
        <div v-if="transcripts_loading">
            <div class="d-flex pa-8 justify-space-around align-center">
              <div>
                <v-progress-circular indeterminate size="32"></v-progress-circular>
                <span class="ms-5">
                  Laden...
                </span>
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
    </div>
  </div>
</template>

<script>
import TranscriptionCard from '@/components/TranscriptionCard.vue'
import axios from 'axios'
import { useUserStore } from '@/stores/user'
import WaveFormComponent from "@/components/WaveFormComponent.vue";

export default {
  name: 'TranscriberView',
  components: {
    WaveFormComponent,
    TranscriptionCard
  },
  data: () => ({
    files_model: [],
    transcriptions: [], // Example: [{id: 1, text: 'Transcription text'}, ...]
    serverStatus: false,
    server_status_loading: true,
    transcripts_loading: true,
    user: useUserStore(),
    server_start_intervall: null
  }),
  computed: {
    selected_file() {
      if (this.files_model.length === 0) return null
      return this.files_model[0]
    }
  },
  mounted() {
    // get server_status
    axios.get('http://localhost:6545/server_status').then((response) => {
      this.serverStatus = response.data.status === 'online'
      this.server_status_loading = false
    })
    // get previous transcriptions
    axios.get('http://localhost:6545/transcriptions', {
      headers: {
        Authorization: 'Bearer ' + this.user.get_user
      }
    }).then((response) => {
      this.transcriptions = response.data
      this.transcripts_loading = false
    })
  },
  methods: {
    server_starting() {
      axios.get('http://localhost:6545/start_server')
      this.server_start_intervall = setInterval(() => {
        axios.get('http://localhost:6545/server_status').then((response) => {
          this.serverStatus = response.data.status === 'online'
          if (this.serverStatus) {
            clearInterval(this.server_start_intervall)
          }
        })
      }, 1000)
    },
  }
}
</script>

<style>

.grid-container {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    //grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    grid-gap: 1em;
    padding: 1em;
}

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
