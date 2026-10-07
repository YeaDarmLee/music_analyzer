import {createApp,h} from 'vue';import AccountGate from './AccountGate.vue';import './style.css';
const legalPages={'/terms':'terms','/privacy':'privacy','/copyright':'copyright','/licenses':'licenses'};
const legal=legalPages[location.pathname.replace(/\/+$/,'')];
if(legal)import('./LegalPage.vue').then(m=>createApp({render:()=>h(m.default,{page:legal})}).mount('#app'));
else createApp(AccountGate).mount('#app');
