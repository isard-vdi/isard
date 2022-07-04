<template>
  <b-col
    cols="8"
    md="5"
    lg="5"
    xl="4"
    class="m-2"
  >
    <div class="bg-white rounded-15 py-4 px-4 text-center">
      <img
        :src="require(`@/assets/img/icons/browser.svg`)"
        alt=""
        class="w-100 m-3"
        style="max-inline-size: fit-content;"
      >
      <b-skeleton
        type="button"
        class="mt-3 w-100"
        style="font-size: 0.8rem;"
      />
    </div>
  </b-col>
</template>

<script>
export default {}
</script>
