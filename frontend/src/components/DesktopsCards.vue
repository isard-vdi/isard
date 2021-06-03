<template>
    <b-container fluid>
      <!---- Card view ---->
      <transition-group v-if="gridView" appear name="bounce">
        <!-- Persistent desktops -->
        <b-row v-if="persistent" key="persistent" align-h="center">
          <isard-card v-for="desktop in desktops" :key="desktop.id" :desktop="desktop" :templates="templates"></isard-card>
        </b-row>
        <!-- Non persistent desktops -->
        <b-row v-else key="nonpersistent" align-h="center">
          <isard-temp-card v-for="desktop in desktops" :key="desktop.id" :desktop="desktop" :templates="templates"></isard-temp-card>
        </b-row>
      </transition-group>

      <!---- Table view ---->
      <b-row v-else>
        <!-- Persistent desktops -->
        <isard-table v-if="persistent" :desktops="desktops"></isard-table>
        <!-- Non persistent desktops -->
        <isard-temp-table v-else :desktops="desktops" :templates="templates"></isard-temp-table>
      </b-row>
    </b-container>
</template>

<script>
// @ is an alias to /src
import IsardCard from '@/components/IsardCard.vue'
import IsardTempCard from '@/components/IsardTempCard.vue'
import IsardTable from '@/components/IsardTable.vue'
import IsardTempTable from '@/components/IsardTempTable.vue'

export default {
  components: { IsardCard, IsardTempCard, IsardTable, IsardTempTable },
  props: {
    templates: {
      required: true,
      type: Array
    },
    desktops: {
      required: true,
      type: Array
    },
    gridView: {
      required: true,
      type: Boolean
    },
    persistent: {
      required: true,
      type: Boolean
    }
  }
}
</script>

<style scoped>
  .bounce-enter-active {
    animation: bounce-in .5s;
  }

  .bounce-leave-active {
    animation: bounce-in .5s reverse;
  }

  @keyframes bounce-in {
    0% {
      transform: scale(0);
    }
    50% {
      transform: scale(1.5);
    }
    100% {
      transform: scale(1);
    }
  }
</style>
