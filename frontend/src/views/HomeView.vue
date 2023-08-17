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
            class="ml-2"
          ></v-progress-circular>
          <div v-else>
            <v-tooltip text="Der Server ist Online" v-if="serverStatus">
              <template v-slot:activator="{ props }">
                <v-icon v-bind="props" class="ml-2" color="success" size="24">mdi-check</v-icon>
              </template>
            </v-tooltip>
            <v-tooltip text="Der Server ist grade ausgeschaltet oder startet grade" v-else>
              <template v-slot:activator="{ props }">
                <v-icon v-bind="props" class="ml-2" color="error" size="24">mdi-close</v-icon>
              </template>
            </v-tooltip>
          </div>
        </div>
      </div>

      <div class="component mb-10">
        <div v-if="transcription_in_progress">
          <div v-show="status === 'transcribing'">
            <div>
              <v-alert type="info" border="start" class="mb-5" icon="mdi-transcribe">
                Die Audio Datei wird grade transcribiert.
              </v-alert>
            </div>
            <v-progress-linear :indeterminate="true" color="purple" height="12"></v-progress-linear>
          </div>
          <div v-show="status === 'done'">
            <div>
              <v-alert type="success" border="start" class="mb-5" icon="mdi-check">
                Die Audio Datei wurde erfolgreich transcribiert.
              </v-alert>
              <div class="d-flex">
                <v-btn
                  variant="tonal"
                  color="success"
                  class="flex-grow-1"
                  prepend-icon="mdi-open-in-app"
                  @click="open_transcript"
                >
                  Öffne Transkriebierung
                </v-btn>
              </div>
            </div>
          </div>
          <div v-show="status === 'error'">
            <div>
              <v-alert type="error" border="start" class="mb-5" icon="mdi-alert">
                Es ist ein Fehler aufgetreten.<br />
                Bitte kontaktiere Freddy.
              </v-alert>
            </div>
          </div>
        </div>
        <div v-else>
          <div v-if="serverStatus">
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
              <WaveFormComponent
                :file="selected_file"
                @transcription_created="transcriptions.push($event)"
              />
            </div>
          </div>
          <div v-else>
            <template v-if="start_server_loading">
              <v-alert type="info" border="start" class="text-body-1 mb-5">
                Der Transcribierungs Server wird gestartet. Das kann einige Sekunden/Minuten dauern.
              </v-alert>
              Laden<span>{{'.'.repeat(start_server_request_amount)}}</span>

              <v-progress-linear indeterminate color="green" height="12"></v-progress-linear>
            </template>
            <template v-else>
              <v-alert type="warning" border="start" class="text-body-1 mb-5">
                Der Transcribierungs Server ist grade ausgeschaltet.
              </v-alert>

              <v-btn
                color="primary"
                class="w-100"
                size="50"
                variant="outlined"
                @click="server_starting"
              >
                <v-icon class="me-5" size="30"> mdi-rocket</v-icon>
                Starte den Transcribierungs Server
              </v-btn>
            </template>
          </div>
        </div>
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
    </div>
  </div>
</template>

<script>
import TranscriptionCard from '@/components/TranscriptionCard.vue'
import axios from 'axios'
import { useUserStore } from '@/stores/user'
import WaveFormComponent from '@/components/WaveFormComponent.vue'

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
    server_start_intervall: null,
    start_server_loading: false,
    start_server_request_amount: 0,
    transcription_in_progress: undefined,
    status: 'idle'
  }),
  computed: {
    selected_file() {
      if (this.files_model.length === 0) return null
      return this.files_model[0]
    }
  },
  mounted() {
    // get server_status
    axios.get(`${import.meta.env.VITE_BACKEND_URL}/server_status`).then((response) => {
      this.serverStatus = response.data.status === 'online'
      this.server_status_loading = false
      this.transcription_in_progress = response.data.transcription_in_progress
      if (this.transcription_in_progress)
        this.get_transcription_in_progress()
    })
    // get previous transcriptions
    axios.get(`${import.meta.env.VITE_BACKEND_URL}/transcriptions`).then((response) => {
      this.transcriptions = response.data
      this.transcripts_loading = false
    })
  },
  methods: {
    server_starting() {
      this.start_server_loading = true
      this.start_server_request_amount++
      axios.get(`${import.meta.env.VITE_BACKEND_URL}/live_server_status`).then((response) => {
        this.serverStatus = response.data.status === 'online'
        if (this.serverStatus) {
          clearInterval(this.server_start_intervall)
          this.start_server_loading = false
        }
      })
      this.server_start_intervall = setInterval(() => {
        this.start_server_request_amount++
        axios.get(`${import.meta.env.VITE_BACKEND_URL}/live_server_status`).then((response) => {
          this.serverStatus = response.data.status === 'online'
          if (this.serverStatus) {
            clearInterval(this.server_start_intervall)
            this.start_server_loading = false
          }
        })
      }, 5000)
    },
    get_transcription_in_progress() {
      this.status = 'transcribing'
      const interval = setInterval(() => {
        axios
          .get(`${import.meta.env.VITE_BACKEND_URL}/transcriptions/${this.transcription_in_progress}`)
          .then((response) => {
            if (response.status !== 202) {
              this.last_transcript = response.data
              this.status = 'done'
              clearInterval(interval)
            }
          })
          .catch(() => {
            this.status = 'error'
            clearInterval(interval)
          })
      }, 1000)
    },
    open_transcript() {
      this.$router.push({
        name: 'transcription',
        params: { transcription_id: this.transcription_in_progress }
      })
    }
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