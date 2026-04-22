// app.js — SPA entry point for /xyz/gallery.
//   * Hash router: '#/' -> MainView (T12: sidebar + filter + folder tree);
//                   '#/image/:id' -> DetailView (T14: zoom + pan + nav);
//                   anything else -> NotFoundView.
//   * Stub WS hookup via api.openWS — the real socket is T18.
// T22: startGalleryConnection() — WS + focus /index/status reconciliation.
// Selection / bulk: T23+.
// Side-effect import: keeps T11 static contract (app.js references ./api.js).
import './api.js';
import { createApp, ref, onMounted } from 'vue';
import { MainView } from './views/MainView.js';
import { DetailView } from './views/DetailView.js';
import { startGalleryConnection } from './stores/connection.js';

function parseHash() {
  const raw = (location.hash || '').replace(/^#/, '');
  if (raw === '' || raw === '/') return { name: 'home' };
  const m = raw.match(/^\/image\/(\d+)$/);
  if (m) return { name: 'detail', id: Number(m[1]) };
  return { name: 'not_found', raw };
}

const route = ref(parseHash());
window.addEventListener('hashchange', () => {
  route.value = parseHash();
});

const NotFoundView = {
  name: 'NotFoundView',
  props: { raw: { type: String, default: '' } },
  template: `
    <section>
      <h2>Not Found</h2>
      <p>No route for: <code>#{{ raw }}</code></p>
      <p><a href="#/">&larr; Home</a></p>
    </section>
  `,
};

const App = {
  name: 'App',
  components: { MainView, DetailView, NotFoundView },
  setup() {
    onMounted(() => {
      startGalleryConnection();
    });
    return { route };
  },
  template: `
    <div class="topbar">
      <a href="#/">XYZ Image Gallery</a>
      <span class="muted">MVP shell</span>
    </div>
    <main class="content">
      <MainView v-if="route.name === 'home'" />
      <DetailView
        v-else-if="route.name === 'detail'"
        :id="route.id"
      />
      <NotFoundView v-else :raw="route.raw || ''" />
    </main>
  `,
};

createApp(App).mount('#app');
