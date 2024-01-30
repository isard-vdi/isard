<template>
  <b-container
    fluid
    class="main-container pl-3 pr-3 pb-5"
  >
    <b-row class="justify-content-center">
      <b-form
        class="w-50"
        @submit.prevent="submitForm"
      >
        <h2 class="mb-2  ml-2">
          <strong>{{ $t('views.disclaimer.title') }}</strong>
        </h2>
        <div
          id="disclaimerWrapper"
          class="p-2 mb-2 mt-2 ml-3"
        >
          <!-- <div style="text-align:left">
            <p>
              En accedir i utilitzar els escriptoris virtuals proporcionats, vostè accepta i es compromet a complir amb els
              següents termes i condicions:
            </p>

            <h4> 1- Ús i Finalitat </h4>
            <ul>
              <li>
                Accepta que utilitzarà els escriptoris virtuals proporcionats exclusivament per a tasques d’àmbit escolar
                relacionades amb els estudis que està cursant actualment en els centres públics del Departament d’Educació.
              </li>
            </ul>
            <h4>2. Confidencialitat i Privacitat</h4>
            <ul>
              <li>
                No deixarà contingut de caràcter privat dins dels escriptoris. És la seva responsabilitat tancar la sessió
                de cada ús i no deixar comptes obertes privades en el navegador, contrasenyes o documents de caràcter
                personal.
              </li>
            </ul>
            <h4>3. Accés i Supervisió</h4>
            <ul>
              <li>
                Els escriptoris virtuals creats per desplegaments del professor podran ser accessibles pel professor
                propietari d’aquest desplegament en qualsevol moment.
              </li>
              <li>
                Els escriptoris virtuals creats i als arxius emmagatzemats per l’usuari seran accessibles pel professor amb
                rol de gestor de la plataforma per a aquell institut. Així mateix, aquests tindran accés a l’activitat
                realitzada per cada usuari a la plataforma amb la finalitat de resoldre incidències i fer un seguiment del
                consum dels recursos associats als escriptoris.
              </li>
              <li> És responsabilitat de l’alumne no deixar material confidencial, sensible o personal en aquests espais.</li>
              <li>
                És responsabilitat del docent i del gestor de centre fer un ús responsable dels desplegaments i l'accés als
                escriptoris dels alumnes.
              </li>
            </ul>
            <h4>4. Còpies de Seguretat i Recuperació de Dades</h4>
            <ul>
              <li>
                No es realitzarà cap còpia de seguretat dels escriptoris, per la qual cosa no es podrà reclamar la seva
                recuperació en cas d’eliminació per error o pèrdua per motius tècnics.
              </li>
            </ul>
            <h4>5. Restriccions d’Ús i Seguretat</h4>
            <ul>
              <li>
                Els escriptoris virtuals no estan dissenyats per a la visualització de vídeos en línia. Això genera un
                consum elevat d’amplada de banda i perjudica el rendiment del servei per a altres usuaris.
              </li>
              <li>
                La navegació per Internet pot estar filtrada i revisada i és responsabilitat de l’usuari no navegar per
                llocs web que no estiguin relacionats amb les tasques educatives.
              </li>
              <li>
                Les credencials d’accés són personals i intransferibles. Es considerarà responsable de qualsevol activitat
                realitzada amb el seu accés personal i ha de notificar qualsevol compromís o sospita de suplantació
                d’identitat.
              </li>
              <li>
                Està prohibit compartir o comunicar les seves credencials. Això inclou no facilitar-les a cap administrador
                o personal de TI.
              </li>
              <li>
                És responsable de la custòdia de les seves credencials, evitant registrar-les en correus electrònics o
                qualsevol altre mitjà també en paper.
              </li>
            </ul>
            <h4>6. Monitoratge de la Navegació</h4>
            <ul>
              <li>
                Els dominis als quals s’accedeix en la navegació per Internet podran ser monitorats pels administradors del
                sistema. Això ajuda a millorar el sistema de filtratge i permet analitzar els dominis si es detecta un ús
                inadequat per part de l’usuari. En tot cas, el contingut d’aquestes comunicacions es mantindrà xifrat,
                analitzant-se només els URL inicials que se sol·liciten en l’inici de la navegació amb cada servidor.
              </li>
            </ul>
            <h4>7. Incompliment de les Normes</h4>
            <ul>
              <li>
                Davant qualsevol ús dels elements de la plataforma d’escriptoris virtuals que contravinguin el que disposa
                aquesta Instrucció o la legislació vigent, els òrgans competents, sense perjudici que adoptin les mesures de
                restricció o de suspensió d’ús que considerin escaients, hauran d’exigir les responsabilitats
                disciplinàries, legals o de qualsevol altre tipus que se’n derivin, d’acord amb la normativa vigent.
              </li>
            </ul>
          </div> -->
        </div>
        <b-button
          type="submit"
          size="md"
          class="btn-green rounded-pill mt-2 ml-2 mr-3 float-right"
          @click="acceptDisclaimer()"
        >
          {{ $t('views.disclaimer.accept') }}
        </b-button>
      </b-form>
    </b-row>
  </b-container>
</template>

<script>

export default {
  setup (_, context) {
  }
}
</script>
