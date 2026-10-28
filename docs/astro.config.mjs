// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightUiTweaks from 'starlight-ui-tweaks'
import starlightScrollToTop from 'starlight-scroll-to-top'
import starlightSidebarTopics from 'starlight-sidebar-topics'
import codeblocks from 'starlight-codeblocks';
import mermaid from 'astro-mermaid';


export default defineConfig({
  site: 'https://blinkseq.github.io/harpy',
  base: '/harpy',
	integrations: [
    mermaid(),
    starlight({
      customCss: ['./src/style/global.css'],
      title: 'Harpy',
      logo: {
        light: '/src/assets/logo_trans.png',
        dark: '/src/assets/logo_trans.png',
        replacesTitle: true
      },
      favicon: '/favicon.png',
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/BLinkseq/harpy' }],
			lastUpdated: true,
      pagination: false,
      editLink: {
        baseUrl: 'https://github.com/blinkseq/harpy/edit/main/docs/',
      },
      plugins: [
        codeblocks(),
        starlightUiTweaks({
        navbarLinks: [
          { label: 'Version: 4.3', href: "javascript:void(0);" },
          { label: "BLink-seq", href: "https://blinkseq.github.io"},
        ],
      }),
        starlightScrollToTop({
          showProgressRing: true,
          progressRingColor: '#83b4eb',
          borderRadius: '50',
        }),
        starlightSidebarTopics([
          {
            label: 'Getting Started',
            link: '/getting-started/install',
            icon: 'information',
            items: [
              {
                label: 'Getting Started',
                items: [
                  { autogenerate: { directory: '/getting-started/' } }
                ]
              },
            ],
          },
          {
            label: 'Commands',
            link: '/commands/',
            icon: 'seti:html',
            items: [
              {
                label: 'Commands',
                items: [
                  { autogenerate: { directory: '/commands/' } }
                ]
              },
            ],
          },
          {
            label: 'Resources',
            link: '/resources/',
            icon: 'open-book',
            items: [
              {
                label: 'Guides',
                items: [
                  { autogenerate: { directory: '/resources/guides' } }
                ]
              },
              {
                label: 'Other',
                items: [
                  { autogenerate: { directory: '/resources/other' } }
                ]
              },

            ],
          },
          {
            label: 'Troubleshoot',
            link: '/troubleshoot/',
            icon: 'warning',
            items: [
              {
                label: 'Troubleshoot',
                items: [
                  { autogenerate: { directory: '/troubleshoot/' } }
                ]
              },
            ],
          },
        ]),
      ],
		}),
	],
});
