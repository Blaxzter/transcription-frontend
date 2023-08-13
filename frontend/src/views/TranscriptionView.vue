<template>
  <v-container :fluid="true" class="fill-height">
    <v-row align="center" justify="center">
      <v-col cols="12" sm="10" md="8">
        <v-card class="elevation-12" style="background-color: rgba(255, 255, 255, 0.8);">
          <v-card-text>
            {{transcription}}
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import axios from 'axios';
import {useUserStore} from "@/stores/user";

export default {
  name: "TranscriptionView",
  data: () => ({
    user: useUserStore(),
    transcription: undefined
  }),
  mounted() {
    axios.get(`http://localhost:6545/transcriptions/${this.$route.params.transcription_id}`, {
      headers: {
        Authorization: 'Bearer ' + this.user.get_user
      }
    })
        .then((response) => {
      this.transcription = response.data;
    });
  },
  methods: {
  }
}
</script>