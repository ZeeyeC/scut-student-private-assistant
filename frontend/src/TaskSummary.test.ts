import {expect,it} from 'vitest';
import {taskCourse} from './TaskSummary';
it('keeps the historical course name after a timetable replacement unlinks the active course',()=>{
 expect(taskCourse({id:'task',kind:'task',revision:2,data:{course_id:null,course_snapshot:{id:'retired',name:'历史课程'}}},[])).toBe('历史课程');
});
