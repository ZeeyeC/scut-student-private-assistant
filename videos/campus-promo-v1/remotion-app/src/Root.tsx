import {Composition, Folder} from 'remotion';
import {Intro, Outro, StylePreview} from './Composition';
import {CampusPromo, HomeworkPreview} from './Promo';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="CampusPromoV1" component={CampusPromo} durationInFrames={2250} fps={30} width={1920} height={1080}/>
      <Composition id="HomeworkPreview" component={HomeworkPreview} durationInFrames={450} fps={30} width={1920} height={1080}/>
      <Composition id="StylePreview" component={StylePreview} durationInFrames={450} fps={30} width={1920} height={1080}/>
      <Folder name="Scenes">
        <Composition id="Intro" component={Intro} durationInFrames={150} fps={30} width={1920} height={1080}/>
        <Composition id="Outro" component={Outro} durationInFrames={150} fps={30} width={1920} height={1080}/>
      </Folder>
    </>
  );
};
