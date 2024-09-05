<script setup lang="ts"></script>

<template>
  <div>
    <!-- Top -->
    <div>
      <!-- Header -->
      <div>
        <img src="https://isardvdi.com/icon.svg" alt="IsardVDI" />
        <button>Collapse</button>
      </div>

      <!-- Top navigation buttons -->
      <div>
        <slot name="header" />
      </div>
    </div>

    <!-- Bottom -->
    <div>
      <!-- Bottom navigation buttons -->
      <div>
        <slot name="footer" />
      </div>

      <!-- Footer -->
      <div>
        <img src="" alt="" />
        <button>Logout</button>
      </div>
    </div>
  </div>
</template>
