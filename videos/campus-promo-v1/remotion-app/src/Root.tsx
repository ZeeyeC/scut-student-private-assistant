import {Composition, Folder} from 'remotion';
import {Intro, Outro, StylePreview} from './Composition';
import {CampusPromo, HomeworkPreview} from './Promo';
import {CampusPromoV2, HomeworkPreviewV2} from './PromoV2';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="CampusPromoV2" component={CampusPromoV2} durationInFrames={1860} fps={30} width={1920} height={1080}/>
      <Composition id="StylePreview" component={CampusPromoV2} durationInFrames={1860} fps={30} width={1920} height={1080}/>
      <Composition id="HomeworkPreview" component={HomeworkPreviewV2} durationInFrames={450} fps={30} width={1920} height={1080}/>
      <Folder name="Earlier">
        <Composition id="CampusPromoV1" component={CampusPromo} durationInFrames={2250} fps={30} width={1920} height={1080}/>
        <Composition id="HomeworkPreviewV1" component={HomeworkPreview} durationInFrames={450} fps={30} width={1920} height={1080}/>
        <Composition id="MaterialStudy" component={StylePreview} durationInFrames={450} fps={30} width={1920} height={1080}/>
      </Folder>
      <Folder name="Scenes">
        <Composition id="Intro" component={Intro} durationInFrames={150} fps={30} width={1920} height={1080}/>
        <Composition id="Outro" component={Outro} durationInFrames={150} fps={30} width={1920} height={1080}/>
      </Folder>
    </>
  );
};
