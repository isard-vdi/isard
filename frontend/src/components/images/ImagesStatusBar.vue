<template>
  <div
    id="statusbar"
    class="px-0 px-lg-5 pl-2"
    style="min-height: 3.6rem;"
  >
    <b-container
      fluid
      class="px-0 py-0"
    >
      <b-navbar
        type="light"
        variant=""
      >
        <div class="separator" />
        <div class="d-flex flex-grow">
          <!-- Left aligned nav items-->
          <b-navbar-nav
            id="statusbar-content"
            class="flex-grow flex-row"
          />

          <!-- Right aligned nav items-->
          <b-navbar-nav class="ml-auto flex-row d-xl-flex">
            <!-- Select file butt web-->
            <div class="d-none d-md-inline pt-1">
              <b-form-group
                label-cols-sm="0"
                label-size="sm"
                class="mb-0"
              >
                <b-form-file
                  v-model="imageFile"
                  :browse-text="$t('components.statusbar.select')"
                  placeholder=""
                  size="sm"
                />
              </b-form-group>
            </div>
            <!-- Select file butt mobile-->
            <div class="d-inline d-md-none pt-1">
              <b-form-group
                label-cols-sm="0"
                label-size="sm"
                class="mb-0"
              >
                <b-form-file
                  v-model="imageFile"
                  browse-text="..."
                  placeholder=""
                  size="sm"
                />
              </b-form-group>
            </div>

            <!-- Upload butt web-->
            <div class="d-none d-md-inline pt-1 pl-3">
              <b-button
                :disabled="imageFile === null"
                :pill="true"
                variant="outline-primary"
                size="sm"
                @click="onClickUploadImageFile()"
              >
                {{ `${$t("components.statusbar.upload-file")}` }}
              </b-button>
            </div>
            <!-- Upload butt mobile-->
            <div class="d-inline d-md-none h3 pt-1 pl-2">
              <b-iconstack
                font-scale="1"
                @click="onClickUploadImageFile()"
              >
                <b-icon
                  stacked
                  icon="circle"
                  :variant="imageFile === null ? '' : 'primary'"
                />
                <b-icon
                  stacked
                  icon="cloud-upload"
                  :variant="imageFile === null ? '' : 'primary'"
                  scale="0.75"
                />
              </b-iconstack>
            </div>

            <!-- Cancel butt web-->
            <div class="d-none d-md-inline pt-1 ml-3">
              <b-button
                :pill="true"
                class="mr-0 mr-md-5"
                variant="outline-danger"
                size="sm"
                @click="navigate('desktops')"
              >
                {{ `${$t("components.statusbar.cancel")}` }}
              </b-button>
            </div>
            <!-- Cancel butt mobile-->
            <div class="d-inline d-md-none h3 pt-1 pl-2">
              <b-icon
                icon="arrow-left-circle"
                variant="danger"
                @click="navigate('desktops')"
              />
            </div>
          </b-navbar-nav>
        </div>
      </b-navbar>
    </b-container>
  </div>
</template>

<script>
import { mapActions } from 'vuex'

export default {
  components: {},
  data () {
    return {
      imageFile: null
    }
  },
  methods: {
    ...mapActions([
      'uploadImageFile',
      'navigate'
    ]),
    onClickUploadImageFile () {
      if (this.imageFile !== null) {
        this.uploadImageFile({ file: this.imageFile, filename: this.imageFile.name })
      }
    }
  }
}
</script>
