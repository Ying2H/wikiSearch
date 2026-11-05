import unittest
from pathlib import Path

from search_sync.extract.content import extract_main_content, stable_record_hash


class ContentTests(unittest.TestCase):
    def test_module_errors_are_not_article_content(self):
        template = "<div id='page-content'><p>正文</p><div class='series'><div class='error-block'>{}</div></div><p>后续正文</p></div>"
        english = extract_main_content(template.format('Parent page hqsbg:{$hqsbgroup} does not exist'))
        chinese = extract_main_content(template.format('父页面 hqsbg:{$hqsbgroup} 不存在'))
        self.assertEqual(english, chinese)
        self.assertEqual(english, '正文\n\n后续正文')

    def test_recent_posts_filter_is_ignored_but_posts_and_other_forms_remain(self):
        template = """<div id='page-content'><div class='forum-recent-posts-box'>
        <form><table><tr><td>{}</td><td><select><option>{}</option></select><input type='button'></td></tr></table></form>
        <div id='forum-recent-posts-list'><p>真实回复内容</p></div></div>
        <form><p>作者编写的表单说明</p></form></div>"""
        english = extract_main_content(template.format('From categories:', 'All categories'))
        chinese = extract_main_content(template.format('来自分类:', '全部分类'))
        self.assertEqual(english, chinese)
        self.assertIn('真实回复内容', english)
        self.assertIn('作者编写的表单说明', english)

    def test_content_extractor_removes_chrome_but_keeps_text(self):
        html = (Path(__file__).parent / "fixtures" / "rendered.html").read_text(encoding="utf-8")
        content = extract_main_content(html)

        self.assertIn("第一段中文内容。", content)
        self.assertIn("第二段正文", content)
        self.assertIn("换行。", content)
        self.assertNotIn("页脚", content)
        self.assertNotIn("编辑控件", content)
        self.assertNotIn("alert", content)

    def test_record_hash_is_stable_across_mapping_order(self):
        self.assertEqual(
            stable_record_hash({"title": "A", "content": "B"}),
            stable_record_hash({"content": "B", "title": "A"}),
        )

    def test_void_tags_do_not_leak_footer_or_drop_following_text(self):
        html = "<div id='page-content'>正文<br>下一行<img src='x'><p>末段</p></div><p>站外页脚</p>"
        self.assertEqual(extract_main_content(html), "正文\n下一行\n末段")

    def test_forum_controls_change_language_without_changing_content(self):
        template = """<div id='page-content'><p>正文</p><div class='comments-box'>
          <div id='comments-options-hidden'>{show}</div><div class='post'><div class='content'>用户评论</div>
          <a href='javascript:;' onclick='WIKIDOT.modules.ForumViewThreadModule.listeners.editPost()'>{edit}</a></div>
          <a id='new-post-button'>{new}</a><div id='post-options-template'>{edit}</div></div></div>"""
        english = extract_main_content(template.format(show='Show Comments', edit='Edit', new='Add a New Comment'))
        chinese = extract_main_content(template.format(show='显示评论', edit='编辑', new='新回复'))
        self.assertEqual(english, chinese)
        self.assertIn('用户评论', english)
        self.assertNotIn('Edit', english)

    def test_wikidot_timestamp_uses_epoch_instead_of_relative_label(self):
        template = "<div id='page-content'>更新于 <span class='odate time_1793115109'>{}</span></div>"
        self.assertEqual(extract_main_content(template.format('3 days ago')), extract_main_content(template.format('4天前')))
        self.assertNotEqual(extract_main_content(template.format('3 days ago')), extract_main_content(template.replace('1793115109', '1793115110').format('3 days ago')))
