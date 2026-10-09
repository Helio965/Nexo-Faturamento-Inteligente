import React from 'react';
import {Composition, registerRoot} from 'remotion';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-700.css';
import '@fontsource/inter/latin-800.css';
import '@fontsource/inter/latin-900.css';
import {NexoFilm} from './NexoFilm';

const Root = () => <Composition id="NexoFilm" component={NexoFilm} durationInFrames={1200} fps={30} width={1920} height={1080}/>;
registerRoot(Root);
