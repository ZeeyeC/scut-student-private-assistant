/** Keep native navigation fixed when locating an item inside a work area. */
export function scrollWithinWorkspace(element:Element|null){
  if(!element)return;
  const container=element.closest<HTMLElement>('.detail-panel-content, #workspace-content');
  if(container)container.scrollTop+=element.getBoundingClientRect().top-container.getBoundingClientRect().top-24;
}
