<script>
import WaveSurfer from 'wavesurfer.js'
import { useUserStore } from '@/stores/user'
import RegionsPlugin from 'wavesurfer.js/plugins/regions'

import HoverPlugin from 'wavesurfer.js/plugins/hover'
import MinimapPlugin from 'wavesurfer.js/plugins/minimap'
import axios from 'axios'

import audioBufferToWav from 'audiobuffer-to-wav'
import router from '@/router'

export default {
  name: 'WaveFormComponent',
  data: () => ({
    user: useUserStore(),

    // wavesurfer stuff
    wavesurfer: null,
    regions: null,
    region: null,

    zoom_level: 1,
    hover_pos: 0,
    audio_duration: 0,
    is_playing: false,

    // Load  audio file
    loading_finished: false,
    loading_percentage: 0,
    loading_intermediate: false,

    // status
    status: 'idle',
    upload_progress: 0,
    last_transcript: null
  }),
  emits: ['transcription_created'],
  props: {
    file: {
      type: Object,
      required: false
    },
    url: {
      type: String,
      required: false
    },
    only_view: {
      type: Boolean,
      required: false,
      default: false
    }
  },
  mounted() {
    this.wavesurfer = WaveSurfer.create({
      container: '#waveform',
      waveColor: '#2196f3',
      progressColor: '#003a69',
      backend: 'MediaElement',
      hideScrollbar: true,
      fetchParams: {
        headers: {
          Authorization: 'Bearer ' + this.user.get_user
        }
      },
      minPxPerSec: 0
    })

    this.regions = this.wavesurfer.registerPlugin(RegionsPlugin.create())
    // this.wavesurfer.registerPlugin(TimelinePlugin.create())
    const hover = this.wavesurfer.registerPlugin(
      HoverPlugin.create({
        lineColor: '#ff0000',
        lineWidth: 2,
        labelBackground: '#555',
        labelColor: '#fff',
        labelSize: '11px'
      })
    )
    hover.on('hover', (position) => {
      this.hover_pos = position
    })

    this.wavesurfer.registerPlugin(
      MinimapPlugin.create({
        height: 20,
        waveColor: '#818181',
        progressColor: '#2c2c2c'
        // the Minimap takes all the same options as the WaveSurfer itself
      })
    )

    this.wavesurfer.on('load', () => {
      console.log('load')
      this.loading_finished = false
    })
    this.wavesurfer.on('ready', () => {
      console.log('ready')
      this.loading_finished = true
    })

    this.wavesurfer.on('decode', (duration) => {
      console.log('decode', duration)
      this.audio_duration = duration

      this.region = this.regions.addRegion({
        start: 0,
        end: this.audio_duration,
        content: `Transkribierungs Bereich`,
        color: 'hsla(203,88%,41%, 0.2)',
        drag: false,
        resize: true
      })
    })

    // add trigger for play pause
    this.wavesurfer.on('play', () => {
      this.is_playing = true
    })
    this.wavesurfer.on('pause', () => {
      this.is_playing = false
    })

    if (this.url) {
      this.wavesurfer.on('loading', (percentage) => {
        console.log('loading', percentage)
        if (percentage === 100) {
          this.loading_intermediate = true
        }
        this.loading_percentage = percentage
      })
      this.wavesurfer.load(this.url)
    } else if (this.file) {
      this.loading_percentage = 100
      this.loading_intermediate = true
      this.wavesurfer.loadBlob(this.file)
    }
  },
  unmounted() {
    this.wavesurfer.destroy()
  },
  computed: {
    loading_percentage_rounded() {
      return this.loading_percentage
    },
    upload_progress_rounded() {
      return this.upload_progress
    }
  },
  methods: {
    open_transcript() {
      console.log(this.last_transcript)
      this.user.set_user_file(this.file)
      router.replace({
        name: 'transcription',
        params: {
          transcription_id: this.last_transcript.id
        }
      })
    },
    async uploadFile() {
      this.status = 'cutting'

      const start = this.region.start
      const end = this.region.end

      // Read the file as a blob
      const reader = new FileReader()
      reader.onload = (event) => {
        // Convert blob to ArrayBuffer
        const arrayBuffer = event.target.result

        // Decode the audio data
        const audioContext = new AudioContext()
        audioContext.decodeAudioData(arrayBuffer, async (buffer) => {
          // Extract the desired segment
          const numberOfChannels = buffer.numberOfChannels
          const sampleRate = buffer.sampleRate
          const startOffset = Math.floor(start * sampleRate)
          const endOffset = Math.floor(end * sampleRate)
          const newBuffer = audioContext.createBuffer(
            numberOfChannels,
            endOffset - startOffset,
            sampleRate
          )

          for (let channel = 0; channel < numberOfChannels; channel++) {
            const oldChannelData = buffer.getChannelData(channel)
            const newChannelData = newBuffer.getChannelData(channel)
            for (let i = startOffset; i < endOffset; i++) {
              newChannelData[i - startOffset] = oldChannelData[i]
            }
          }

          // Encode the segment to WAV format
          // This function needs to be defined to convert the audio buffer to WAV or other desired format
          const wavArrayBuffer = audioBufferToWav(newBuffer)
          const wavBlob = new Blob([wavArrayBuffer], { type: 'audio/wav' })
          // Create FormData and append the audio segment
          const formData = new FormData()
          formData.append('file', wavBlob, `${this.file.name}`)

          // Now you can upload the formData using fetch or any other AJAX method
          this.status = 'uploading'

          await axios
            .post(`http://localhost:6545/transcribe`, formData, {
              headers: {
                'content-type': 'multipart/form-data', // do not forget this
                Authorization: 'Bearer ' + this.user.get_user
              },
              onUploadProgress: (progressEvent) => {
                this.upload_progress = Math.round(
                  (progressEvent.loaded / progressEvent.total) * 100
                )
              }
            })
            .then((response) => {
              this.status = 'transcribing'
              this.start_check_for_update(response.data.transcription_id)
            })
            .catch((err) => {
              this.status = 'error'
              console.log(err)
            })
        })
      }

      // Read the audio file as an ArrayBuffer
      reader.readAsArrayBuffer(this.file)
    },
    start_check_for_update(transcription_id) {
      const interval = setInterval(() => {
        axios
          .get(`http://localhost:6545/transcriptions/${transcription_id}`)
          .then((response) => {
            console.log(response)
            if (response.status === 202) {
              console.log("Waiting for transcription to finish")
            } else {
              this.status = 'done'
              this.last_transcript = response.data
              clearInterval(interval)
            }
          })
          .catch((err) => {
            console.log(err)
            this.status = 'error'
            clearInterval(interval)
          })
      }, 1000)
    },
    onWheel: function (e) {
      let delta = -Math.max(-1, Math.min(1, e.deltaY))
      this.zoom_level = this.zoom_level + delta
      this.zoom_level = Math.max(0, Math.min(200, this.zoom_level))
      this.wavesurfer.zoom(this.zoom_level)
    },
    playPause() {
      console.log('playPause')
      this.wavesurfer.playPause()
    }
  }
}
</script>

<template>
  <div v-show="status === 'idle'">
    <div v-show="loading_finished">
      <div v-if="!only_view">
        <h2 class="mb-5">Audio Datei</h2>
        <div class="text-body-1">
          Schiebe den Blauen bereich um die Audio Datei zu trimmen. Mit dem click auf Starte
          Transkriebierung wird die Datei geschnitten und hochgeladen.
        </div>
      </div>
      <div id="waveform" @wheel="onWheel" />
      <div v-if="wavesurfer" class="d-flex">
        <v-btn
          color="primary"
          class="mt-5"
          :prepend-icon="is_playing ? 'mdi-stop' : 'mdi-play'"
          @click="playPause"
        >
          {{ is_playing ? 'Stop' : 'Play' }}
        </v-btn>
      </div>
    </div>
    <div v-show="!loading_finished">
      <div>
        <v-alert type="info" border="start">
          <span v-if="loading_percentage_rounded < 100">
            Die Audio Datei wird heruntergeladen...
          </span>
          <span v-else>
            Die Audio Welle wird geladen... Das kann einige Sekunden dauern. Jeh nach länger der
            Datei
          </span>
        </v-alert>
      </div>
      <div class="mt-5">
        <v-progress-linear
          v-if="loading_intermediate"
          :indeterminate="true"
          color="success"
          height="12"
        ></v-progress-linear>
        <v-progress-linear v-else v-model="loading_percentage_rounded" color="purple" height="24">
          <template v-slot:default="{ value }">
            <strong>{{ Math.ceil(value) }}%</strong>
          </template>
        </v-progress-linear>
      </div>
    </div>

    <v-btn
      class="w-100 mt-5"
      variant="tonal"
      prepend-icon="mdi-send"
      @click="uploadFile"
      v-if="!only_view"
    >
      Starte Transcribierung
    </v-btn>
  </div>
  <div v-show="status === 'cutting'">
    <div>
      <v-alert type="info" border="start" class="mb-5" icon="mdi-scissors-cutting">
        Die Audio Datei wird grade geschnitten.
      </v-alert>
    </div>
  </div>
  <div v-show="status === 'uploading'">
    <div>
      <v-alert type="info" border="start" class="mb-5" icon="mdi-rocket">
        Die Audio Datei wird grade hochgeladen.
      </v-alert>
    </div>
    <v-progress-linear
      v-model="upload_progress_rounded"
      color="purple"
      height="12"
    ></v-progress-linear>
  </div>
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
        <v-btn
          class="flex-grow-1 ms-2"
          color="warning"
          variant="tonal"
          prepend-icon="mdi-repeat"
          @click="this.status = 'idle'"
        >
          Neuen Bereich wählen
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
</template>

<style>
#waveform ::part(hover-label):before {
  content: '⏱️ ';
}

#waveform {
  overflow: visible;
}

#waveform ::part(region-content) {
  position: absolute;
  //content: 'Transcribierungs Bereich';
  margin-top: -24px !important;
}
</style>